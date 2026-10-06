"""员工在 Admin Platform 回复病人（Phase 5）。WhatsApp 换成假的，不会真的发出去。"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select, update

from app.db.demo import add_demo_data
from app.db.models import Message, Sender, WaStatus
from app.db.seed import seed
from app.whatsapp import RecipientNotAllowed, WhatsAppError, get_whatsapp_client
from tests.database import PASSWORD, add_staff


class FakeWhatsApp:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []
        self.error: Exception | None = None

    def send_text(self, to: str, body: str) -> str:
        if self.error:
            raise self.error
        self.sent.append((to, body))
        return f"wamid.fake.{len(self.sent)}"


@pytest.fixture
def whatsapp():
    from app.main import app

    fake = FakeWhatsApp()
    app.dependency_overrides[get_whatsapp_client] = lambda: fake
    return fake          # client_for 结束时会清掉 dependency_overrides


@pytest.fixture
def amy(session, client_for, whatsapp):
    seed(session)
    add_demo_data(session, date(2026, 10, 5))
    add_staff(session, "amy", password=PASSWORD)
    return client_for("amy")


def conversation_id(client, name, mode=None):
    rows = client.get("/api/conversations", params={"mode": mode} if mode else {}).json()
    return next(c["id"] for c in rows if c["profile_name"] == name)


def test_reply_sends_and_takes_over(amy, whatsapp):
    mum = conversation_id(amy, "Demo Mum")                     # AI 在回复的对话
    r = amy.post(f"/api/conversations/{mum}/reply", json={"body": "  Hi! Friday 4pm is confirmed.  "})
    assert r.status_code == 200, r.text
    detail = r.json()
    assert whatsapp.sent == [("60120000001", "Hi! Friday 4pm is confirmed.")]
    last = detail["messages"][-1]
    assert (last["sender"], last["body"], last["wa_status"]) == ("STAFF", "Hi! Friday 4pm is confirmed.", "ACCEPTED")
    assert detail["mode"] == "HUMAN" and detail["assigned_staff_name"] == "amy (test)"     # 回复 = 接手（D22）
    assert detail["reply_window_ends_at"] is not None


def test_first_staff_reply_to_handed_over_conversation_assigns_it(amy, whatsapp):
    sg = conversation_id(amy, "Demo SG")                       # AI 转给员工、还没有人负责
    assert amy.get(f"/api/conversations/{sg}").json()["assigned_staff_name"] is None
    detail = amy.post(f"/api/conversations/{sg}/reply", json={"body": "Hi, this is the clinic."}).json()
    assert detail["mode"] == "HUMAN" and detail["assigned_staff_name"] == "amy (test)"
    assert detail["handover_reason"] == "Patient is in pain and asked for a human"      # 原因留着


def test_no_reply_after_24_hours(amy, whatsapp, session):
    mum = conversation_id(amy, "Demo Mum")
    session.execute(update(Message).where(Message.sender == Sender.CUSTOMER)
                    .values(created_at=Message.created_at - timedelta(hours=25)))
    r = amy.post(f"/api/conversations/{mum}/reply", json={"body": "Hello"})
    assert r.status_code == 409 and "24 hours" in r.json()["detail"]
    assert whatsapp.sent == []


def test_no_reply_to_closed_conversation(amy, whatsapp):
    closed = conversation_id(amy, "Demo Cancel", mode="CLOSED")
    assert amy.post(f"/api/conversations/{closed}/reply", json={"body": "Hello"}).status_code == 409
    assert whatsapp.sent == []


def test_failed_send_is_not_saved(amy, whatsapp, session):
    mum = conversation_id(amy, "Demo Mum")
    before = session.scalars(select(Message.id)).all()
    whatsapp.error = WhatsAppError("Recipient phone number not in allowed list")
    r = amy.post(f"/api/conversations/{mum}/reply", json={"body": "Hello"})
    assert r.status_code == 502 and "not in allowed list" in r.json()["detail"]
    whatsapp.error = RecipientNotAllowed("This number is not in WHATSAPP_ALLOWED_RECIPIENTS")
    assert amy.post(f"/api/conversations/{mum}/reply", json={"body": "Hello"}).status_code == 409
    assert session.scalars(select(Message.id)).all() == before              # 没发出去就不存
    assert amy.get(f"/api/conversations/{mum}").json()["mode"] == "BOT"     # 也没有接手


def test_reply_needs_text_and_login(amy, client_for):
    mum = conversation_id(amy, "Demo Mum")
    assert amy.post(f"/api/conversations/{mum}/reply", json={"body": "   "}).status_code == 422
    assert amy.post(f"/api/conversations/{mum}/reply", json={"body": "x" * 4097}).status_code == 422
    assert client_for().post(f"/api/conversations/{mum}/reply", json={"body": "Hello"}).status_code == 401


def test_detail_shows_delivery_status_fields(amy):
    mum = conversation_id(amy, "Demo Mum")
    first = amy.get(f"/api/conversations/{mum}").json()["messages"][0]
    assert first["wa_status"] is None and first["wa_error"] is None          # 病人发来的消息没有送达状态
