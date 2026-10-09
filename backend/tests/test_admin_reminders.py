"""Admin API：提醒名单（GET /api/reminders）。假的 GPiS、假名字、假号码。"""

from datetime import date

import pytest

from app.api.reminders import get_reminder_source
from app.config import WhatsAppSettings, get_whatsapp_settings
from app.db.seed import seed
from app.main import app
from app.reminders import ReminderAppointment
from tests.database import PASSWORD, add_staff

FRI = date(2026, 10, 9)


class FakeSource:
    def __init__(self, rows=(), production=False, error=None):
        self.rows, self.error, self.calls = list(rows), error, []
        self.is_production = production
        self.label = "GPiS" if production else "GPiS_Dev"

    def reminder_appointments(self, first, last):
        self.calls.append((first, last))
        if self.error:
            raise self.error
        return self.rows


def row(i, time_slot="10:00", doctor="PHANG", name="Demo Patient A", phone="012-000 0001", remarks="S+P (P)",
        day=FRI):
    return ReminderAppointment(i, day, time_slot, doctor, "Confirmed", 5000 + i, name, phone, remarks)


ROWS = [
    row(1),
    row(2, "10:30", doctor="GOH", name="Demo Patient B"),
    row(3, "11:00", name="Demo Patient C", phone="012-000 0003", remarks="ISSUE CROWN 36 (P)"),
    row(4, "00:00", remarks="REMIND PT STO"),
]


def wa(allowed):
    return WhatsAppSettings("v", "s", "t", "p", "v26.0", allowed)


@pytest.fixture
def amy(session, client_for):
    seed(session)
    add_staff(session, "amy", password=PASSWORD)
    return client_for("amy")


def use(source, allowed=frozenset()):
    app.dependency_overrides[get_reminder_source] = lambda: source
    app.dependency_overrides[get_whatsapp_settings] = lambda: wa(allowed)
    return source


def test_needs_login(session, client_for):
    assert client_for().get("/api/reminders").status_code == 401


def test_preview_list(amy):
    src = use(FakeSource(ROWS))
    body = amy.get("/api/reminders", params={"date": "2026-10-09"}).json()
    assert src.calls == [(FRI, FRI)]
    assert body["dates"] == ["2026-10-09"] and body["source"] == "GPiS_Dev" and body["production"] is False

    [family] = body["ready"]
    assert family["phone"] == "60120000001" and family["phone_kind"] == "MY_MOBILE"
    assert [(ln["time"], ln["doctor_name"], ln["patient_name"]) for ln in family["lines"]] == [
        ("10:00", "PHANG", "DEMO PATIENT A"), ("10:30", "GOH", "DEMO PATIENT B")]
    assert "NAME: DEMO PATIENT A & DEMO PATIENT B" in family["message"]
    assert family["whatsapp_allowed"] is False           # GPiS_Dev：不能打开真的病人的 WhatsApp（D54）

    [lab] = body["needs_staff"]
    assert lab["problems"] == ["Lab work not marked as arrived (*C)"] and lab["whatsapp_allowed"] is False
    assert body["not_appointments"] == [{"reason": "To-do at 00:00", "count": 1}]
    assert "ISSUE CROWN" not in str(body)                # Remarks 不出现在回应里


def test_whatsapp_lock(amy):
    """读 GPiS_Dev / 假资料时，只有写在允许名单里的号码才有 Open in WhatsApp；* 也不算（D54）。"""
    params = {"date": "2026-10-09"}
    use(FakeSource(ROWS), allowed=frozenset({"60120000001"}))
    assert amy.get("/api/reminders", params=params).json()["ready"][0]["whatsapp_allowed"] is True
    use(FakeSource(ROWS), allowed=None)                  # WHATSAPP_ALLOWED_RECIPIENTS=*
    assert amy.get("/api/reminders", params=params).json()["ready"][0]["whatsapp_allowed"] is False
    use(FakeSource(ROWS, production=True))
    body = amy.get("/api/reminders", params=params).json()
    assert body["ready"][0]["whatsapp_allowed"] is True
    assert body["needs_staff"][0]["whatsapp_allowed"] is False    # 要员工看的永远没有


def test_default_date_is_tomorrow(amy, monkeypatch):
    monkeypatch.setattr("app.api.reminders.clinic_today", lambda: date(2026, 10, 8))
    src = use(FakeSource(ROWS))
    body = amy.get("/api/reminders").json()
    assert body["dates"] == body["suggested_dates"] == ["2026-10-09"]
    assert src.calls == [(FRI, FRI)]


def test_holiday_dates(session, client_for, monkeypatch):
    from app.db.models import ClinicClosure
    seed(session)
    session.add(ClinicClosure(closure_date=FRI, reason="Demo holiday"))
    session.flush()
    add_staff(session, "amy", password=PASSWORD)
    amy = client_for("amy")
    monkeypatch.setattr("app.api.reminders.clinic_today", lambda: date(2026, 10, 8))
    src = use(FakeSource([row(1, day=date(2026, 10, 10))]))
    body = amy.get("/api/reminders").json()
    assert body["suggested_dates"] == body["dates"] == ["2026-10-09", "2026-10-10"]
    assert src.calls == [(FRI, date(2026, 10, 10))]
    assert body["ready"][0]["date"] == "2026-10-10"


def test_gpis_error_hides_details(amy):
    use(FakeSource(error=RuntimeError("Server=secret;PWD=hunter2")))
    r = amy.get("/api/reminders", params={"date": "2026-10-09"})
    assert r.status_code == 503 and "hunter2" not in r.text


# ---------- 员工做过的事：Open in WhatsApp、没有发出去、不要提醒（reminders 表、D55） ----------

KEY = {"date": "2026-10-09", "phone": "60120000001"}
OWN = frozenset({"60120000001"})


def ready_family(client):
    body = client.get("/api/reminders", params={"date": "2026-10-09"}).json()
    return next(g for g in body["ready"] + body["needs_staff"] if g["phone"] == "60120000001"), body


def test_open_in_whatsapp_is_recorded(amy, session):
    from app.db.models import Reminder
    use(FakeSource(ROWS), allowed=OWN)
    family, _ = ready_family(amy)
    assert family["record"] is None and family["opted_out"] is False

    r = amy.post("/api/reminders/opened", json={"date": "2026-10-09", "phone": "+60 12-000 0001"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "OPENED" and r.json()["staff_name"] == "amy (test)"

    family, _ = ready_family(amy)
    assert family["record"]["status"] == "OPENED" and family["record"]["changed"] is False
    [row] = session.query(Reminder).all()
    assert row.gpis_appointment_ids == [1, 2] and "NAME: DEMO PATIENT A & DEMO PATIENT B" in row.body


def test_second_open_updates_the_same_row(amy, session, client_for):
    from app.db.models import Reminder
    use(FakeSource(ROWS), allowed=OWN)
    add_staff(session, "ben", password=PASSWORD)
    ben = client_for("ben")
    assert amy.post("/api/reminders/opened", json=KEY).status_code == 200
    assert ben.post("/api/reminders/opened", json=KEY).json()["staff_name"] == "ben (test)"
    assert session.query(Reminder).count() == 1       # 同一个号码、同一天只有一条（D45）
    family, _ = ready_family(amy)
    assert family["record"]["staff_name"] == "ben (test)"


def test_list_changed_after_opening(amy):
    use(FakeSource(ROWS), allowed=OWN)
    amy.post("/api/reminders/opened", json=KEY)
    use(FakeSource(ROWS + [row(5, "11:30", name="Demo Patient E")]), allowed=OWN)   # 同一个号码多了一个预约
    family, _ = ready_family(amy)
    assert family["record"]["changed"] is True


def test_open_is_refused_when_not_ready_or_locked(amy):
    use(FakeSource(ROWS), allowed=OWN | {"60120000003"})
    lab = {"date": "2026-10-09", "phone": "60120000003"}          # 没有 *C → Needs staff
    assert amy.post("/api/reminders/opened", json=lab).status_code == 409
    use(FakeSource(ROWS))                                          # 不在允许名单（D54）
    assert amy.post("/api/reminders/opened", json=KEY).status_code == 403
    use(FakeSource(ROWS, production=True))
    assert amy.post("/api/reminders/opened", json=KEY).status_code == 200
    assert amy.post("/api/reminders/opened", json={"date": "2026-10-09", "phone": "abc"}).status_code == 422


def test_mark_not_sent(amy):
    use(FakeSource(ROWS), allowed=OWN)
    assert amy.post("/api/reminders/not-sent", json=KEY).status_code == 404     # 还没按过
    amy.post("/api/reminders/opened", json=KEY)
    assert amy.post("/api/reminders/not-sent", json=KEY).json()["status"] == "NOT_SENT"
    family, _ = ready_family(amy)
    assert family["record"]["status"] == "NOT_SENT"


def test_no_wa_moves_the_number_to_needs_staff(amy):
    use(FakeSource(ROWS), allowed=OWN)
    r = amy.put("/api/reminders/opt-out", json={"phone": "012-000 0001", "opted_out": True})
    assert r.json() == {"phone": "60120000001", "opted_out": True}
    family, body = ready_family(amy)
    assert family in body["needs_staff"] and family["opted_out"] is True
    assert family["problems"] == ["Opted out of reminders"] and family["whatsapp_allowed"] is False
    assert amy.post("/api/reminders/opened", json=KEY).status_code == 409

    amy.put("/api/reminders/opt-out", json={"phone": "60120000001", "opted_out": False})
    family, body = ready_family(amy)
    assert family in body["ready"] and family["opted_out"] is False


def test_actions_need_login(session, client_for):
    anon = client_for()
    assert anon.post("/api/reminders/opened", json=KEY).status_code == 401
    assert anon.post("/api/reminders/not-sent", json=KEY).status_code == 401
    assert anon.put("/api/reminders/opt-out", json={"phone": "60120000001", "opted_out": True}).status_code == 401
