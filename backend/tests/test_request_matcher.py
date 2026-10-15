"""每 3 分钟找 GPiS 的预约（D70）、PENDING 算占用（A8）。全部是假名字、假号码、假的预约来源。"""

from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app import request_matcher as rm
from app.db import conversations as conv
from app.db.appointment_requests import (
    InvalidTransition, cancel_request, confirm_request, create_appointment_request, mark_patient_notified,
    pending_holds, reject_request,
)
from app.db.customers import create_customer
from app.db.models import AppointmentRequest, Customer, DoneBy, Message, RequestStatus, Sender, WaStatus
from app.db.seed import seed
from app.matching import BookedAppointment
from app.reminders import CLINIC_TZ, ReminderText
from app.whatsapp import RecipientNotAllowed, WhatsAppError, WhatsAppNotConfigured
from tests.database import PASSWORD, add_staff, assert_rejected

TODAY = date(2026, 10, 19)
DAY = date(2026, 10, 21)            # 星期三
PHONE = "60120000001"
TEXT = ReminderText()


class FakeSource:
    """假的 GPiS：只回给的预约，记下每次问了哪一天、哪几位病人。"""

    def __init__(self, appointments=(), error=None):
        self.appointments, self.error, self.calls = list(appointments), error, []

    def patient_appointments(self, day, contact_ids):
        self.calls.append((day, frozenset(contact_ids)))
        if self.error:
            raise self.error
        return [a for a in self.appointments if a.appointment_date == day and a.contact_id in contact_ids]


class FakeWhatsApp:
    def __init__(self, error=None):
        self.error, self.sent = error, []

    def send_text(self, to, body):
        if self.error:
            raise self.error
        self.sent.append((to, body))
        return f"wamid.confirm.{len(self.sent)}"


def booked(aid=7001, contact=501, day=DAY, slot="10:00", doctor="PHANG", status="Confirmed"):
    return BookedAppointment(aid, day, slot, doctor, status, contact, "S+P (P)")


@pytest.fixture
def db(session):
    seed(session)
    return session


def new_request(db, contact=501, slot=time(10, 0), day=DAY, doctor="PHANG", phone=PHONE, wamid="wamid.in.1",
                duration=30):
    """病人从 WhatsApp 来（24 小时内传过消息），AI 建了一个 PENDING 请求。"""
    msg, _ = conv.record_incoming_message(db, phone, "Book S+P please", wamid)
    patient = db.query(Customer).filter_by(gpis_contact_id=contact).one_or_none() or create_customer(
        db, f"Demo Patient {contact}", phone, gpis_contact_id=contact)
    return create_appointment_request(db, patient, "S+P", conversation=msg.conversation, doctor_id=doctor,
                                      preferred_date=day, preferred_slot=slot, duration_minutes=duration)


def run(db, source, whatsapp=None, dry_run=False):
    db.commit()       # 准备的资料先存起来（run_once 自己会 commit / rollback）
    return rm.run_once(db, source, whatsapp or FakeWhatsApp(), TEXT, today=TODAY, dry_run=dry_run)


# ---------- A8：PENDING 算占用 ----------

def test_only_pending_requests_with_a_slot_and_doctor_hold_a_place(db):
    staff = add_staff(db)
    a = new_request(db, 501, wamid="w1")
    b = new_request(db, 502, slot=time(15, 0), duration=60, wamid="w2")
    for change, contact in ((lambda r: confirm_request(db, r, staff), 503),
                            (lambda r: reject_request(db, r, staff), 504),
                            (lambda r: cancel_request(db, r), 505)):
        change(new_request(db, contact, wamid=f"w{contact}"))
    new_request(db, 506, doctor="GOH", wamid="w6")                  # 别的医生
    new_request(db, 507, day=DAY + timedelta(days=1), wamid="w7")   # 别的日子
    patient = create_customer(db, "Demo No Slot")
    create_appointment_request(db, patient, "S+P", doctor_id="PHANG", preferred_date=DAY)   # 没有时段
    create_appointment_request(db, patient, "S+P", preferred_date=DAY, preferred_slot=time(11, 0))  # 没有医生

    holds = pending_holds(db, DAY, " phang ")
    assert [(h.request_id, h.slot, h.dur_slots) for h in holds] == [(a.id, time(10, 0), 1), (b.id, time(15, 0), 2)]


# ---------- 找到 → CONFIRMED → 发确认 ----------

def test_found_in_gpis_is_confirmed_and_patient_told(db):
    r = new_request(db)
    wa = FakeWhatsApp()
    result = run(db, FakeSource([booked()]), wa)

    db.refresh(r)
    assert (r.status, r.confirmed_by, r.gpis_appointment_id, r.handled_by) == (
        RequestStatus.CONFIRMED, DoneBy.SYSTEM, 7001, None)
    assert r.handled_at is not None
    assert (r.patient_notified_by, r.notify_problem) == (DoneBy.SYSTEM, None) and r.patient_notified_at
    assert (result.requests, result.days, result.confirmed, result.notified, result.to_notify) == (
        1, 1, [r.id], [r.id], [])
    assert pending_holds(db, DAY, "PHANG") == []          # 确认了就不再另外算（GPiS 已经有了）

    [(to, body)] = wa.sent
    assert to == PHONE and "DATE: 21/10/26 (Wed)" in body and "TIME: 10:00 AM" in body
    saved = db.query(Message).filter_by(wa_message_id="wamid.confirm.1").one()
    assert (saved.sender, saved.wa_status, saved.body) == (Sender.BOT, WaStatus.ACCEPTED, body)


def test_confirmation_is_sent_even_after_staff_took_over(db):
    """AI 没开时对话都交给员工（HUMAN）：确认是系统的通知，照发。"""
    r = new_request(db)
    conv.take_over(db, r.conversation, None)
    wa = FakeWhatsApp()
    run(db, FakeSource([booked()]), wa)
    assert len(wa.sent) == 1


def test_only_asks_gpis_for_the_request_dates_and_patients(db):
    new_request(db, 501, wamid="w1")
    new_request(db, 502, slot=time(11, 0), wamid="w2")
    new_request(db, 503, day=DAY + timedelta(days=2), wamid="w3")
    new_request(db, 504, day=TODAY - timedelta(days=1), wamid="w4")     # 已经过了的日子不找
    new_patient = create_customer(db, "Demo New Patient", PHONE)         # 新病人没有 ContactID：员工按
    create_appointment_request(db, new_patient, "S+P", doctor_id="PHANG", preferred_date=DAY,
                               preferred_slot=time(9, 0))
    src = FakeSource()
    result = run(db, src)
    assert src.calls == [(DAY, frozenset({501, 502})), (DAY + timedelta(days=2), frozenset({503}))]
    assert (result.requests, result.days, result.confirmed) == (3, 2, [])


def test_nothing_found_stays_pending(db):
    r = new_request(db)
    result = run(db, FakeSource([booked(slot="10:30"), booked(status="Canceled", aid=7002)]))
    db.refresh(r)
    assert r.status == RequestStatus.PENDING and result.confirmed == []
    assert [h.request_id for h in pending_holds(db, DAY, "PHANG")] == [r.id]


def test_appointment_already_used_by_another_request_is_left_to_staff(db):
    """例：改期时 GPiS 的 AppointmentID 不变（W5），旧的请求已经记着这个预约。"""
    staff = add_staff(db)
    old = new_request(db, 501, slot=time(9, 0), wamid="w1")
    confirm_request(db, old, staff, gpis_appointment_id=7001)
    r = new_request(db, 501, wamid="w2")
    run(db, FakeSource([booked()]))
    db.refresh(r)
    assert r.status == RequestStatus.PENDING


def test_one_gpis_appointment_is_never_on_two_requests(db):
    staff = add_staff(db)
    a = new_request(db, 501, wamid="w1")
    b = new_request(db, 502, wamid="w2")
    confirm_request(db, a, staff, gpis_appointment_id=7001)
    b.status, b.confirmed_by, b.gpis_appointment_id, b.handled_at = (
        RequestStatus.CONFIRMED, DoneBy.STAFF, 7001, datetime.now(timezone.utc))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.flush()


def test_dry_run_changes_nothing(db):
    r = new_request(db)
    wa = FakeWhatsApp()
    result = run(db, FakeSource([booked()]), wa, dry_run=True)
    db.refresh(r)
    assert result.confirmed == [r.id] and r.status == RequestStatus.PENDING and wa.sent == []


def test_gpis_error_changes_nothing(db):
    r = new_request(db)
    with pytest.raises(RuntimeError):
        run(db, FakeSource(error=RuntimeError("cannot reach GPiS")))
    db.rollback()
    db.refresh(r)
    assert r.status == RequestStatus.PENDING


def test_staff_who_confirms_at_the_same_time_wins_or_loses_cleanly(db):
    """员工先按了：系统看到不是 PENDING，就不改、不发。"""
    staff = add_staff(db)
    r = new_request(db)
    db.commit()
    matches = rm.find_in_gpis(db, FakeSource([booked()]), TODAY, 34094, rm.MatchResult())
    confirm_request(db, r, staff)
    result = rm.MatchResult()
    rm.confirm_matches(db, matches, result)
    db.refresh(r)
    assert result.confirmed == [] and (r.confirmed_by, r.gpis_appointment_id) == (DoneBy.STAFF, None)


# ---------- 发不了 → 要员工通知 ----------

def _age_last_message(db, hours):
    db.execute(update(Message).values(created_at=datetime.now(timezone.utc) - timedelta(hours=hours)))


@pytest.mark.parametrize("prepare,whatsapp,problem", [
    (lambda db, r: _age_last_message(db, 25), FakeWhatsApp(), rm.WINDOW_CLOSED),
    (lambda db, r: conv.close_conversation(db, r.conversation), FakeWhatsApp(), rm.CONVERSATION_CLOSED),
    (None, FakeWhatsApp(WhatsAppNotConfigured("not set up")), rm.NOT_CONNECTED),       # 电脑 B 现在就是
    (None, FakeWhatsApp(RecipientNotAllowed("not allowed")), rm.NOT_ALLOWED),
    (None, FakeWhatsApp(WhatsAppError("Re-engagement message (code 131047)")),
     "WhatsApp did not accept the message: Re-engagement message (code 131047)"),
])
def test_cannot_send_means_staff_must_tell_the_patient(db, prepare, whatsapp, problem):
    r = new_request(db)
    if prepare:
        prepare(db, r)
    whatsapp.sent = []
    result = run(db, FakeSource([booked()]), whatsapp)
    db.refresh(r)
    assert r.status == RequestStatus.CONFIRMED and r.confirmed_by == DoneBy.SYSTEM
    assert (r.patient_notified_at, r.notify_problem) == (None, problem)
    assert (result.notified, result.to_notify) == ([], [r.id]) and whatsapp.sent == []
    assert db.query(Message).filter(Message.sender == Sender.BOT).count() == 0


def test_request_not_from_whatsapp_is_left_for_staff_to_tell(db):
    patient = create_customer(db, "Demo Phone Booking", gpis_contact_id=501)
    r = create_appointment_request(db, patient, "S+P", doctor_id="PHANG", preferred_date=DAY,
                                   preferred_slot=time(10, 0))
    run(db, FakeSource([booked()]))
    db.refresh(r)
    assert (r.status, r.notify_problem) == (RequestStatus.CONFIRMED, rm.NO_CONVERSATION)


def test_staff_marks_patient_told(db):
    staff = add_staff(db)
    r = new_request(db)
    _age_last_message(db, 30)
    run(db, FakeSource([booked()]))
    db.refresh(r)
    mark_patient_notified(db, r, staff)
    assert (r.patient_notified_by, r.patient_notified_staff_id, r.notify_problem) == (DoneBy.STAFF, staff.id, None)
    with pytest.raises(InvalidTransition):
        mark_patient_notified(db, r, staff)          # 按两次


def test_pending_request_cannot_be_marked_told(db):
    with pytest.raises(InvalidTransition):
        mark_patient_notified(db, new_request(db))


@pytest.mark.parametrize("values", [
    {"status": RequestStatus.CONFIRMED, "handled_at": datetime.now(timezone.utc)},     # 没写谁确认的
    {"confirmed_by": DoneBy.SYSTEM},                                                    # PENDING 不能有
    {"status": RequestStatus.CONFIRMED, "handled_at": datetime.now(timezone.utc), "confirmed_by": DoneBy.SYSTEM,
     "patient_notified_at": datetime.now(timezone.utc)},                               # 缺 patient_notified_by
    {"status": RequestStatus.CONFIRMED, "handled_at": datetime.now(timezone.utc), "confirmed_by": DoneBy.SYSTEM,
     "patient_notified_at": datetime.now(timezone.utc), "patient_notified_by": DoneBy.SYSTEM,
     "patient_notified_staff_id": "staff"},                                            # 系统通知的没有员工
])
def test_database_rejects_inconsistent_rows(db, values):
    patient = create_customer(db, "Demo Patient")
    if values.get("patient_notified_staff_id") == "staff":
        values = {**values, "patient_notified_staff_id": add_staff(db).id}
    assert_rejected(db, AppointmentRequest(customer_id=patient.id, service_code="S+P", **values))


# ---------- 营业时间、API ----------

@pytest.mark.parametrize("local,expected", [
    (time(8, 59), False), (time(9, 0), True), (time(17, 29), True), (time(17, 30), False), (time(23, 0), False),
])
def test_only_runs_in_business_hours(local, expected):
    now = datetime.combine(DAY, local, tzinfo=CLINIC_TZ).astimezone(timezone.utc)
    assert rm.in_business_hours(now) is expected


def test_matcher_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("REQUEST_MATCHER", "off")
    assert rm.start_background() is None


def test_requests_api_shows_who_confirmed_and_notified(db, client_for):
    add_staff(db, "amy", password=PASSWORD)
    r = new_request(db)
    _age_last_message(db, 25)
    run(db, FakeSource([booked()]))
    [row] = client_for("amy").get("/api/requests", params={"status": "CONFIRMED"}).json()
    assert row["id"] == r.id
    assert (row["confirmed_by"], row["patient_notified_at"], row["notify_problem"]) == (
        "SYSTEM", None, rm.WINDOW_CLOSED)
    # 已经被系统确认了，员工再按 Confirm：409（不会改成员工确认）
    assert client_for("amy").post(f"/api/requests/{r.id}/confirm").status_code == 409


def test_staff_confirm_records_staff(db, client_for):
    add_staff(db, "amy", password=PASSWORD)
    r = new_request(db)
    db.commit()
    row = client_for("amy").post(f"/api/requests/{r.id}/confirm").json()
    assert (row["status"], row["confirmed_by"], row["patient_notified_at"]) == ("CONFIRMED", "STAFF", None)


def test_cli_needs_once():
    with pytest.raises(SystemExit):
        rm.main([])
