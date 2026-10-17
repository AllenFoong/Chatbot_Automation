"""自动确认（Phase 6a-2c，D71 ②、D74）。GPiS、WhatsApp 都换成假的；全部是假名字、假号码。"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import select

from app import auto_confirm
from app.auto_confirm import PendingFacts, has_treatment, in_business_hours, plan, run_once
from app.db import conversations as conv
from app.db.appointment_requests import create_appointment_request, reopen_request, cancel_request
from app.db.customers import create_customer
from app.db.models import AppointmentRequest, ClinicSettings, Message, RequestStatus, Sender
from app.db.seed import seed
from app.reminders import ReminderAppointment
from tests.database import PASSWORD, add_staff

FRI = date(2026, 10, 23)
NOW = datetime(2026, 10, 19, 3, 0, tzinfo=timezone.utc)          # 星期一 11:00（马来西亚时间）
CLINIC = 34094
PHONE = "60120000077"


def row(i, slot="11:30", doctor="PHANG", contact=990001, remarks="S+P (P)", day=FRI, status="Confirmed",
        name="DEMO AUTO"):
    return ReminderAppointment(i, day, slot, doctor, status, contact, name, "0120000077", remarks)


def facts(request_id=1, contact=990001, slot=time(11, 30), doctor="PHANG", code="S+P", minutes=30, before=False):
    return PendingFacts(request_id, contact, FRI, slot, doctor, code, minutes, before)


# ---------- 比对规则（不连数据库） ----------

@pytest.mark.parametrize("remarks,code,expected", [
    ("S+P (P) WITH", "S+P", True),
    ("OR(P)", "OR", True),
    ("ORTHO REVIEW", "OR", False),
    ("FOR CHECK", "OR", False),
    ("C/UP AFTER ISSUE DENTURE", "C/UP", True),
    ("ISSUE CROWN 36 (P) *C", "ISSUE CROWN", True),
    ("SCAN B 33-37 (P)", "SCAN B", True),
    ("RCT (C) 36,SC 36 (P)", "SC", True),
    ("RCT (C) 36,SC 36 (P)", "SCAN B", False),
    (None, "S+P", False),
])
def test_treatment_code_in_remarks(remarks, code, expected):
    assert has_treatment(remarks, code) is expected


def test_first_look_only_records_whether_the_day_already_had_an_appointment():
    p = plan([facts(1, before=None), facts(2, contact=5, before=None)], [row(1)], set(), CLINIC)
    assert p.baselines == {1: True, 2: False} and p.matches == {}


def test_everything_the_same_is_confirmed():
    p = plan([facts()], [row(101), row(102, contact=7)], set(), CLINIC)
    assert list(p.matches) == [1] and p.matches[1].appointment_id == 101


@pytest.mark.parametrize("change", [
    {"slot": "12:00"}, {"doctor": "GOH"}, {"remarks": "C/UP (P)"}, {"remarks": "S+P 1 HOUR"},
    {"status": "Canceled"}, {"contact": CLINIC}, {"day": FRI + timedelta(days=1)},
])
def test_anything_different_waits_for_staff(change):
    assert plan([facts()], [row(101, **change)], set(), CLINIC).matches == {}


def test_one_hour_request_needs_one_hour_in_gpis():
    assert plan([facts(minutes=60)], [row(101, remarks="S+P 1HOUR")], set(), CLINIC).matches[1].appointment_id == 101
    assert plan([facts(minutes=60)], [row(101)], set(), CLINIC).matches == {}


def test_already_used_or_already_there_is_not_confirmed():
    assert plan([facts()], [row(101)], {101}, CLINIC).matches == {}
    assert plan([facts(before=True)], [row(101)], set(), CLINIC).matches == {}


def test_ambiguous_matches_wait_for_staff():
    """一个预约对得上两个请求、或一个请求对得上两个预约（D70）。"""
    assert plan([facts(1), facts(2)], [row(101)], set(), CLINIC).matches == {}
    assert plan([facts(1)], [row(101), row(102)], set(), CLINIC).matches == {}


def test_business_hours_in_malaysia_time():
    def at(hh, mm):
        return datetime(2026, 10, 19, hh, mm, tzinfo=timezone(timedelta(hours=8)))

    assert not in_business_hours(at(8, 59))
    assert in_business_hours(at(9, 0)) and in_business_hours(at(17, 29))
    assert not in_business_hours(at(17, 30))


# ---------- 跑一次（测试数据库 + 假的 GPiS、WhatsApp） ----------

class FakeSource:
    label, is_production, fake_data = "Demo data", False, True

    def __init__(self, rows=()):
        self.rows = list(rows)

    def reminder_appointments(self, first, last):
        return [r for r in self.rows if first <= r.appointment_date <= last]


class FakeWhatsApp:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send_text(self, to, body):
        self.sent.append((to, body))
        return f"wamid.auto.{len(self.sent)}"


@pytest.fixture
def db(session):
    seed(session)
    return session


def new_request(db, contact=990001, slot=time(11, 30)):
    msg, _ = conv.record_incoming_message(db, PHONE, "Book scaling please", f"wamid.in.{slot}{contact}")
    patient = create_customer(db, "Demo Auto", PHONE, gpis_contact_id=contact)
    return create_appointment_request(db, patient, "S+P", conversation=msg.conversation, doctor_id="PHANG",
                                      preferred_date=FRI, preferred_slot=slot)


def test_first_look_then_confirm_when_staff_enters_it_in_gpis(db):
    r = new_request(db)
    wa = FakeWhatsApp()

    result, _ = run_once(db, FakeSource(), wa, NOW)              # 员工还没输入 GPiS
    assert result.first_looks == 1 and result.confirmed == [] and r.gpis_same_day_before is False

    result, _ = run_once(db, FakeSource([row(101)]), wa, NOW)    # 员工输入了
    assert result.confirmed == [r.id]
    db.refresh(r)
    assert r.status == RequestStatus.CONFIRMED and r.handled_by is None          # 系统确认的
    assert (r.gpis_appointment_id, r.confirmed_slot, r.confirmed_doctor_id) == (101, time(11, 30), "PHANG")
    assert r.patient_told_at is not None and r.notify_problem is None
    [(to, text)] = wa.sent
    assert to == PHONE and text.startswith("好的哟") and "TIME: 11:30 AM" in text
    msg = db.scalar(select(Message).where(Message.wa_message_id == "wamid.auto.1"))
    assert msg.sender == Sender.BOT                               # AI 模式的对话：算系统发的，AI 照常继续

    result, _ = run_once(db, FakeSource([row(101)]), wa, NOW)    # 再跑一次：不会重复
    assert result.looked_at == 0 and len(wa.sent) == 1


def test_appointment_already_there_at_first_look_is_left_to_staff(db):
    r = new_request(db)
    wa = FakeWhatsApp()
    run_once(db, FakeSource([row(101)]), wa, NOW)                  # 第一次看就已经有了（可能是旧的）
    result, _ = run_once(db, FakeSource([row(101)]), wa, NOW)
    assert r.gpis_same_day_before is True and result.confirmed == [] and wa.sent == []
    assert db.get(AppointmentRequest, r.id).status == RequestStatus.PENDING


def test_dry_run_changes_nothing(db):
    r = new_request(db)
    db.commit()
    result, decided = run_once(db, FakeSource(), None, NOW, dry_run=True)
    assert decided.baselines == {r.id: False} and db.get(AppointmentRequest, r.id).gpis_same_day_before is None


def test_requests_without_contact_or_in_the_past_are_skipped(db):
    r = new_request(db)
    r.customer.gpis_contact_id = None                              # 新病人：员工第一次按的时候才记下 ContactID
    result, _ = run_once(db, FakeSource(), FakeWhatsApp(), NOW)
    assert result.looked_at == 0
    r.customer.gpis_contact_id = 990001
    result, _ = run_once(db, FakeSource(), FakeWhatsApp(), NOW + timedelta(days=10))      # 日期过了
    assert result.looked_at == 0


def test_staff_confirmed_first_is_not_confirmed_again(db, monkeypatch):
    r = new_request(db)
    wa = FakeWhatsApp()
    run_once(db, FakeSource(), wa, NOW)
    original = auto_confirm.plan

    def staff_presses_meanwhile(*args, **kwargs):
        decided = original(*args, **kwargs)
        cancel_request(db, db.get(AppointmentRequest, r.id))     # 员工在两步之间改了这个请求
        db.commit()
        return decided

    monkeypatch.setattr(auto_confirm, "plan", staff_presses_meanwhile)
    result, decided = run_once(db, FakeSource([row(101)]), wa, NOW)
    assert list(decided.matches) == [r.id] and result.confirmed == [] and wa.sent == []


def test_back_to_pending_looks_again(db):
    r = new_request(db)
    run_once(db, FakeSource(), FakeWhatsApp(), NOW)
    cancel_request(db, r)
    reopen_request(db, r)
    assert r.gpis_same_day_before is None


# ---------- 背景每 3 分钟（tick） ----------

@pytest.fixture
def tick_env(db, monkeypatch):
    @contextmanager
    def same_session():
        yield db

    wa = FakeWhatsApp()
    source = FakeSource([row(101)])
    monkeypatch.setattr("app.db.session.new_session", same_session)
    monkeypatch.setattr(auto_confirm, "_source_or_none", lambda: source)
    monkeypatch.setattr("app.whatsapp.get_whatsapp_client", lambda: wa)
    return wa, source


def test_tick_does_nothing_when_off_or_after_hours(db, tick_env):
    new_request(db)
    assert auto_confirm.tick(NOW) is None                          # 开关默认关
    db.get(ClinicSettings, 1).auto_confirm = True
    assert auto_confirm.tick(NOW.replace(hour=11)) is None         # 19:00：下班了


def test_tick_records_the_last_check_and_errors(db, tick_env):
    wa, source = tick_env
    r = new_request(db)
    settings = db.get(ClinicSettings, 1)
    settings.auto_confirm = True
    assert auto_confirm.tick(NOW).first_looks == 1 and settings.auto_confirm_checked_at is not None
    assert settings.auto_confirm_error is None

    def broken(first, last):
        raise RuntimeError("Server=a;PWD=hunter2")

    source.reminder_appointments = broken
    assert auto_confirm.tick(NOW) is None
    assert "Could not check GPiS" in settings.auto_confirm_error and "hunter2" not in settings.auto_confirm_error
    assert db.get(AppointmentRequest, r.id).status == RequestStatus.PENDING


def test_tick_does_not_run_on_gpis_dev(db, tick_env, monkeypatch):
    class GpisDev:
        label, is_production = "GPiS_Dev", False

    monkeypatch.setattr(auto_confirm, "_source_or_none", lambda: GpisDev())
    new_request(db)
    db.get(ClinicSettings, 1).auto_confirm = True
    assert auto_confirm.tick(NOW) is None


# ---------- 页面上的状态、只有 ADMIN 能开 ----------

def test_status_line_and_admin_only_switch(db, client_for, monkeypatch):
    from app.api.requests import get_confirm_source
    from app.main import app
    from app.db.models import StaffRole

    add_staff(db, "boss", role=StaffRole.ADMIN, password=PASSWORD)
    add_staff(db, "amy", password=PASSWORD)
    boss, amy = client_for("boss"), client_for("amy")
    app.dependency_overrides[get_confirm_source] = lambda: FakeSource()
    monkeypatch.setattr(auto_confirm, "datetime", _FrozenDatetime)

    body = amy.get("/api/requests/auto-confirm").json()
    assert body["enabled"] is False and body["runs_here"] is True and body["stale"] is False

    assert amy.patch("/api/settings", json={"auto_confirm": True}).status_code == 403     # STAFF 不能开
    assert boss.patch("/api/settings", json={"auto_confirm": True}).json()["auto_confirm"] is True
    body = amy.get("/api/requests/auto-confirm").json()
    assert body["enabled"] is True and body["checked_at"] is None and body["stale"] is True   # 还没查过

    db.get(ClinicSettings, 1).auto_confirm_checked_at = NOW - timedelta(minutes=5)
    assert amy.get("/api/requests/auto-confirm").json()["stale"] is False
    db.get(ClinicSettings, 1).auto_confirm_checked_at = NOW - timedelta(minutes=20)
    assert amy.get("/api/requests/auto-confirm").json()["stale"] is True


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is None else NOW.astimezone(tz)


def test_auto_confirm_in_a_staff_conversation_is_recorded_as_staff(db):
    from app.db.models import Conversation, ConversationMode

    r = new_request(db)
    conversation = db.get(Conversation, r.conversation_id)
    conv.take_over(db, conversation, None)
    assert conversation.mode == ConversationMode.HUMAN
    wa = FakeWhatsApp()
    run_once(db, FakeSource(), wa, NOW)
    run_once(db, FakeSource([row(101)]), wa, NOW)
    msg = db.scalar(select(Message).where(Message.wa_message_id == "wamid.auto.1"))
    assert msg.sender == Sender.STAFF and msg.staff_id is None    # 不知道是哪一位员工：系统发的
    assert conversation.mode == ConversationMode.HUMAN


def test_demo_scenario_for_the_dev_computer(db, monkeypatch):
    """python -m app.db.demo --auto-confirm-demo <自己的手机>：第一次看（没有）→ 员工「输入」→ 自动确认、发消息。"""
    from app.db.demo import auto_confirm_demo

    wa = FakeWhatsApp()
    conv.record_incoming_message(db, PHONE, "test 6a-2c", "wamid.self.6a2c")
    lines = auto_confirm_demo(db, PHONE, FRI, wa)
    assert lines[0].startswith("Added pending request") and "first look" in lines[1]
    assert "confirmed automatically" in lines[2] and "sent" in lines[2]
    [(to, text)] = wa.sent
    assert to == PHONE and "NAME: DEMO AUTO" in text and "TIME: 11:30 AM" in text
    assert auto_confirm_demo(db, "60120000999", FRI, wa) == [
        "No open conversation for that number: send a WhatsApp message to the test number first."]
