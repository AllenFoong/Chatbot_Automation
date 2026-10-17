"""员工按 Entered in GPiS ✓：当场查 GPiS、点选、确认、通知病人（Phase 6a-2b，D71 ①）。

GPiS、WhatsApp 都换成假的；用 app/db/demo.py 的假资料（Demo Kid A / B：PHANG 10-09 16:00，号码 60120000001；
Demo Patient：GOH 10-10 10:00，ContactID 900001，号码 60120000002）。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.api.requests import get_confirm_source
from app.config import WhatsAppSettings, get_whatsapp_settings
from app.db.appointment_requests import create_appointment_request
from app.db.customers import create_customer
from app.db.demo import add_demo_data
from app.db.models import AppointmentRequest, Conversation, ConversationMode, Customer, Message, Sender
from app.db.seed import seed
from app.main import app
from app.reminders import ReminderAppointment
from app.whatsapp import RecipientNotAllowed, WhatsAppError, WhatsAppNotConfigured, get_whatsapp_client
from tests.database import PASSWORD, add_staff

TODAY = date(2026, 10, 5)
FRI, SAT = date(2026, 10, 9), date(2026, 10, 10)
OWN_PHONE = "60120000001"          # Demo Mum 的号码，当作开发者自己的手机（允许名单）


class FakeSource:
    def __init__(self, rows=(), production=False, fake_data=True, error=None):
        self.rows, self.error, self.calls = list(rows), error, []
        self.is_production, self.fake_data = production, fake_data
        self.label = "GPiS" if production else ("Demo data" if fake_data else "GPiS_Dev")

    def reminder_appointments(self, first, last):
        self.calls.append((first, last))
        if self.error:
            raise self.error
        return [r for r in self.rows if first <= r.appointment_date <= last]


class FakeWhatsApp:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []
        self.error: Exception | None = None

    def send_text(self, to: str, body: str) -> str:
        if self.error:
            raise self.error
        self.sent.append((to, body))
        return f"wamid.confirm.{len(self.sent)}"


def row(i, slot="16:00", doctor="PHANG", contact=5000 + 1, name="DEMO KID A (P)", day=FRI, status="Confirmed",
        remarks="S+P SECRET REMARK"):
    return ReminderAppointment(i, day, slot, doctor, status, contact, name, "0120000001", remarks)


ROWS = [
    row(101),                                                   # Demo Kid A 在 GPiS 的预约
    row(102, contact=5002, name="DEMO KID B"),
    row(103, slot="10:00", doctor="GOH", contact=7777, name="SOMEONE ELSE"),
    row(104, status="Canceled", name="CANCELLED ONE"),
    row(201, slot="10:30", doctor="GOH", contact=900001, name="DEMO PATIENT", day=SAT),
]


@pytest.fixture
def whatsapp():
    fake = FakeWhatsApp()
    app.dependency_overrides[get_whatsapp_client] = lambda: fake
    return fake


@pytest.fixture
def amy(session, client_for, whatsapp):
    seed(session)
    add_demo_data(session, TODAY)
    add_staff(session, "amy", password=PASSWORD)
    return client_for("amy")


def use(source, allowed=frozenset({OWN_PHONE})):
    app.dependency_overrides[get_confirm_source] = lambda: source
    app.dependency_overrides[get_whatsapp_settings] = lambda: WhatsAppSettings("v", "s", "t", "p", "v26.0", allowed)
    return source


def pending(client, name):
    return next(r for r in client.get("/api/requests").json() if r["customer_name"] == name)


def to_tell(client):
    return client.get("/api/requests", params={"to_tell": "true"}).json()


# ---------- 点选的名单 ----------

def test_gpis_list_puts_the_matching_appointment_first(amy):
    src = use(FakeSource(ROWS))
    kid = pending(amy, "Demo Kid A")
    r = amy.get(f"/api/requests/{kid['id']}/gpis")
    assert r.status_code == 200
    body = r.json()
    assert src.calls == [(FRI, FRI)]
    assert body["date"] == "2026-10-09" and body["source"] == "Demo data" and body["can_notify"] is True
    assert [c["appointment_id"] for c in body["choices"]] == [101, 102, 103]        # 取消的不列
    first = body["choices"][0]
    assert first["time"] == "16:00" and first["doctor_name"] == "PHANG" and first["patient_name"] == "DEMO KID A"
    assert first["same_doctor"] and first["same_time"] and not first["same_patient"]  # Kid A 还没有 ContactID
    assert "SECRET" not in r.text and "0120000001" not in r.text                     # 没有 Remarks、号码


def test_gpis_list_for_another_date_and_known_patient(amy):
    use(FakeSource(ROWS))
    patient = pending(amy, "Demo Patient")                       # ContactID 900001，请求是 GOH 10-10 10:00
    body = amy.get(f"/api/requests/{patient['id']}/gpis").json()
    c = body["choices"][0]
    assert c["appointment_id"] == 201 and c["same_patient"] and c["same_doctor"] and not c["same_time"]
    assert amy.get(f"/api/requests/{patient['id']}/gpis", params={"date": "2026-10-09"}).json()["date"] \
        == "2026-10-09"


def test_request_without_date_needs_a_date(amy, session):
    use(FakeSource(ROWS))
    p = create_customer(session, "Demo No Date", "60120000009")
    r = create_appointment_request(session, p, "C/UP")
    session.commit()                  # 出错的 API 会 rollback 没存的资料
    assert amy.get(f"/api/requests/{r.id}/gpis").status_code == 422
    assert amy.get(f"/api/requests/{r.id}/gpis", params={"date": "2026-10-09"}).status_code == 200


def test_gpis_errors(amy):
    kid = pending(amy, "Demo Kid A")
    use(FakeSource(error=RuntimeError("Server=a;PWD=hunter2")))
    r = amy.get(f"/api/requests/{kid['id']}/gpis")
    assert r.status_code == 503 and "hunter2" not in r.text
    use(None)                                                    # 这台电脑没设定 GPiS：看得到请求，不能确认
    assert amy.get(f"/api/requests/{kid['id']}/gpis").status_code == 503
    assert len(amy.get("/api/requests").json()) == 3


# ---------- 确认 + 通知 ----------

def test_confirm_sends_the_confirmation(amy, whatsapp, session):
    use(FakeSource(ROWS))
    kid = pending(amy, "Demo Kid A")
    r = amy.post(f"/api/requests/{kid['id']}/confirm", json={"gpis_appointment_id": 101})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "CONFIRMED" and body["gpis_appointment_id"] == 101
    assert (body["confirmed_date"], body["confirmed_slot"], body["confirmed_doctor_id"]) == ("2026-10-09", "16:00:00",
                                                                                              "PHANG")
    assert body["patient_told_at"] is not None and body["patient_told_by"] is None and body["notify_problem"] is None
    assert body["gpis_contact_id"] == 5001                      # 新病人：记下 GPiS 的 ContactID
    assert body["whatsapp_allowed"] is False                    # 已经通知了，不用再按
    [(to, text)] = whatsapp.sent
    assert to == OWN_PHONE and "NAME: DEMO KID A" in text and "TIME: 4:00 PM" in text and "DR PHANG" in text
    assert to_tell(amy) == []

    # 消息存进对话：AI 在回复的对话 → 算 AI（系统）发的，AI 照常继续
    msg = session.scalars(select(Message).where(Message.wa_message_id == "wamid.confirm.1")).one()
    assert msg.sender == Sender.BOT and msg.body == text
    assert session.get(Conversation, msg.conversation_id).mode == ConversationMode.BOT


def test_confirm_in_a_staff_conversation_is_sent_as_staff(amy, whatsapp, session):
    use(FakeSource(ROWS))
    kid = pending(amy, "Demo Kid A")
    session.execute(update(Conversation).where(Conversation.id == kid["conversation_id"])
                    .values(mode=ConversationMode.HUMAN))
    amy.post(f"/api/requests/{kid['id']}/confirm", json={"gpis_appointment_id": 101})
    msg = session.scalars(select(Message).where(Message.wa_message_id == "wamid.confirm.1")).one()
    assert msg.sender == Sender.STAFF and msg.staff_id is not None


def test_not_in_gpis_cannot_be_confirmed(amy, whatsapp):
    use(FakeSource(ROWS))
    kid = pending(amy, "Demo Kid A")
    for gpis_id in (999, 104):                                  # 没有、已经取消
        r = amy.post(f"/api/requests/{kid['id']}/confirm", json={"gpis_appointment_id": gpis_id})
        assert r.status_code == 409 and "Enter it in GPiS first" in r.json()["detail"]
    assert pending(amy, "Demo Kid A")["status"] == "PENDING" and whatsapp.sent == []


def test_one_gpis_appointment_confirms_one_request(amy, whatsapp):
    use(FakeSource(ROWS))
    kid_a, kid_b = pending(amy, "Demo Kid A"), pending(amy, "Demo Kid B")
    assert amy.post(f"/api/requests/{kid_a['id']}/confirm", json={"gpis_appointment_id": 101}).status_code == 200
    choices = amy.get(f"/api/requests/{kid_b['id']}/gpis").json()["choices"]
    assert next(c for c in choices if c["appointment_id"] == 101)["used_by_request_id"] == kid_a["id"]
    r = amy.post(f"/api/requests/{kid_b['id']}/confirm", json={"gpis_appointment_id": 101})
    assert r.status_code == 409 and "another request" in r.json()["detail"]
    assert amy.post(f"/api/requests/{kid_a['id']}/confirm", json={"gpis_appointment_id": 101}).status_code == 409


def test_staff_can_pick_another_time_doctor_or_date(amy, whatsapp):
    """员工约成别的时间、医生、日期：照点选的那个确认、通知。"""
    use(FakeSource(ROWS))
    patient = pending(amy, "Demo Patient")
    r = amy.post(f"/api/requests/{patient['id']}/confirm", json={"gpis_appointment_id": 103, "date": "2026-10-09"})
    body = r.json()
    assert (body["confirmed_date"], body["confirmed_slot"], body["confirmed_doctor_id"]) == ("2026-10-09", "10:00:00",
                                                                                              "GOH")
    assert body["gpis_contact_id"] == 900001                     # 已经有 ContactID 的不改
    [(to, text)] = whatsapp.sent
    assert to == "60120000002" and "DATE: 09/10/26" in text and "TIME: 10:00 AM" in text and "DR GOH" in text


def test_contact_id_used_by_another_patient_is_not_copied(amy, session):
    use(FakeSource(ROWS))
    create_customer(session, "Demo Other", "60120000008", gpis_contact_id=5001)
    kid = pending(amy, "Demo Kid A")
    assert amy.post(f"/api/requests/{kid['id']}/confirm", json={"gpis_appointment_id": 101}).json()[
        "gpis_contact_id"] is None


@pytest.mark.parametrize("source,error,problem", [
    (FakeSource(ROWS, fake_data=False), None, "GPiS_Dev"),                     # 真的病人名字：不发
    (FakeSource(ROWS), RecipientNotAllowed("x"), "WHATSAPP_ALLOWED_RECIPIENTS"),
    (FakeSource(ROWS), WhatsAppNotConfigured("x"), "not set up"),
    (FakeSource(ROWS), WhatsAppError("bad token (code 190)"), "bad token (code 190)"),
])
def test_not_sent_goes_to_tell_list(amy, whatsapp, source, error, problem):
    use(source)
    whatsapp.error = error
    kid = pending(amy, "Demo Kid A")
    body = amy.post(f"/api/requests/{kid['id']}/confirm", json={"gpis_appointment_id": 101}).json()
    assert body["status"] == "CONFIRMED" and body["patient_told_at"] is None
    assert problem in body["notify_problem"]
    assert [r["id"] for r in to_tell(amy)] == [kid["id"]]
    assert whatsapp.sent == []


def test_gpis_dev_has_no_open_in_whatsapp(amy):
    use(FakeSource(ROWS, fake_data=False))
    kid = pending(amy, "Demo Kid A")
    amy.post(f"/api/requests/{kid['id']}/confirm", json={"gpis_appointment_id": 101})
    [r] = to_tell(amy)
    assert r["whatsapp_allowed"] is False and r["whatsapp_phone"] == OWN_PHONE and "DEMO KID A" in r["confirm_message"]


def test_over_24_hours_staff_tells_the_patient(amy, whatsapp, session):
    use(FakeSource(ROWS, production=True, fake_data=False), allowed=None)
    kid = pending(amy, "Demo Kid A")
    old = datetime.now(timezone.utc) - timedelta(days=2)
    session.execute(update(Message).where(Message.conversation_id == kid["conversation_id"]).values(created_at=old))
    body = amy.post(f"/api/requests/{kid['id']}/confirm", json={"gpis_appointment_id": 101}).json()
    assert "More than 24 hours" in body["notify_problem"] and whatsapp.sent == []
    [r] = to_tell(amy)
    assert r["whatsapp_allowed"] is True                         # 正式资料：员工用 Open in WhatsApp

    told = amy.post(f"/api/requests/{kid['id']}/patient-told")
    assert told.status_code == 200 and told.json()["patient_told_at"] is not None
    assert told.json()["patient_told_by"] is not None and told.json()["whatsapp_allowed"] is False
    assert to_tell(amy) == []
    assert amy.post(f"/api/requests/{kid['id']}/patient-told").status_code == 409


def test_closed_conversation_and_staff_added_request(amy, whatsapp, session):
    use(FakeSource(ROWS))
    kid = pending(amy, "Demo Kid A")
    session.execute(update(Conversation).where(Conversation.id == kid["conversation_id"])
                    .values(mode=ConversationMode.CLOSED, closed_at=datetime.now(timezone.utc)))
    assert "closed" in amy.post(f"/api/requests/{kid['id']}/confirm",
                                json={"gpis_appointment_id": 101}).json()["notify_problem"]

    p = create_customer(session, "Demo Phone Booking", OWN_PHONE)
    r = create_appointment_request(session, p, "S+P", doctor_id="PHANG", preferred_date=FRI)
    body = amy.post(f"/api/requests/{r.id}/confirm", json={"gpis_appointment_id": 102}).json()
    assert "No WhatsApp conversation" in body["notify_problem"]
    assert body["whatsapp_phone"] == OWN_PHONE and body["whatsapp_allowed"] is True
    assert whatsapp.sent == []


def test_saving_after_send_fails_keeps_it_in_tell_list(amy, whatsapp, monkeypatch):
    use(FakeSource(ROWS))

    def broken(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("app.confirming.conv.record_outgoing_message", broken)
    kid = pending(amy, "Demo Kid A")
    body = amy.post(f"/api/requests/{kid['id']}/confirm", json={"gpis_appointment_id": 101}).json()
    assert body["status"] == "CONFIRMED" and len(whatsapp.sent) == 1
    assert "Check the WhatsApp chat" in body["notify_problem"]
    assert [r["id"] for r in to_tell(amy)] == [kid["id"]]


def test_cancelled_after_confirm_leaves_the_tell_list(amy):
    use(FakeSource(ROWS, fake_data=False))
    kid = pending(amy, "Demo Kid A")
    amy.post(f"/api/requests/{kid['id']}/confirm", json={"gpis_appointment_id": 101})
    assert amy.post(f"/api/requests/{kid['id']}/cancel").json()["status"] == "CANCELLED"
    assert to_tell(amy) == []


def test_confirmed_requests_hold_no_slot(amy, session):
    """确认之后不再算占用（GPiS 里已经有了，A8）。"""
    from app.db.appointment_requests import held_requests

    use(FakeSource(ROWS, fake_data=False))
    assert len(held_requests(session, FRI, "PHANG")) == 2
    kid = pending(amy, "Demo Kid A")
    amy.post(f"/api/requests/{kid['id']}/confirm", json={"gpis_appointment_id": 101})
    assert [h.request_id for h in held_requests(session, FRI, "PHANG")] == [pending(amy, "Demo Kid B")["id"]]
    assert session.get(AppointmentRequest, kid["id"]).customer.gpis_contact_id == 5001
    assert session.scalar(select(Customer.gpis_contact_id).where(Customer.name == "Demo Kid A")) == 5001


def test_demo_request_for_own_phone(session):
    """开发电脑测「确认后自动通知」用：python -m app.db.demo --request-for <自己的手机>。"""
    from app.db import conversations as conv
    from app.db.demo import add_request_for

    seed(session)
    assert add_request_for(session, "60129999999", FRI) is None          # 还没有对话
    conv.record_incoming_message(session, "60129999999", "hi", "wamid.self.1")
    first = add_request_for(session, "60129999999", FRI)
    second = add_request_for(session, "60129999999", FRI)                 # 同一位 Demo Self
    rows = session.scalars(select(AppointmentRequest).where(AppointmentRequest.id.in_([first, second]))).all()
    assert {r.customer_id for r in rows} == {rows[0].customer_id}
    assert rows[0].doctor_id == "PHANG" and rows[0].preferred_date == FRI and rows[0].conversation_id is not None


def test_back_to_pending_after_a_wrong_cancel_or_reject(amy, session):
    """按错了 Cancel / Reject：Back to pending 改回来，又算占用（A8）。"""
    from app.db.appointment_requests import held_requests

    use(FakeSource(ROWS))
    kid_a, kid_b = pending(amy, "Demo Kid A"), pending(amy, "Demo Kid B")
    assert amy.post(f"/api/requests/{kid_a['id']}/cancel").json()["status"] == "CANCELLED"
    assert amy.post(f"/api/requests/{kid_b['id']}/reject").json()["status"] == "REJECTED"
    assert held_requests(session, FRI, "PHANG") == []
    for kid in (kid_a, kid_b):
        r = amy.post(f"/api/requests/{kid['id']}/reopen")
        assert r.status_code == 200
        assert r.json()["status"] == "PENDING" and r.json()["handled_at"] is None
    assert len(held_requests(session, FRI, "PHANG")) == 2
    assert amy.post(f"/api/requests/{kid_a['id']}/reopen").status_code == 409     # 已经是 PENDING


def test_back_to_pending_after_confirm_and_cancel_clears_the_confirmation(amy, whatsapp):
    use(FakeSource(ROWS))
    kid = pending(amy, "Demo Kid A")
    amy.post(f"/api/requests/{kid['id']}/confirm", json={"gpis_appointment_id": 101})
    assert amy.post(f"/api/requests/{kid['id']}/reopen").status_code == 409      # CONFIRMED 要先取消
    amy.post(f"/api/requests/{kid['id']}/cancel")
    body = amy.post(f"/api/requests/{kid['id']}/reopen").json()
    assert body["status"] == "PENDING"
    assert body["gpis_appointment_id"] is None and body["confirmed_date"] is None
    assert body["confirm_message"] is None and body["patient_told_at"] is None and body["notify_problem"] is None
    # 可以再确认一次（同一个 GPiS 预约），再发一次确认
    assert amy.post(f"/api/requests/{kid['id']}/confirm", json={"gpis_appointment_id": 101}).status_code == 200
    assert len(whatsapp.sent) == 2
