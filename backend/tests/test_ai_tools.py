"""6a-3a：AI 查空档的两个工具（全部是假资料）。"""

from datetime import date, time, timedelta

import pytest

from app import ai_tools
from app.ai_tools import ToolContext
from app.availability import GpisAppointment
from app.db.appointment_requests import create_appointment_request
from app.db.customers import create_customer
from app.db.models import ClinicClosure, Doctor, Service
from app.db.seed import seed

TODAY = date(2026, 10, 21)      # 星期三
THU = date(2026, 10, 22)        # PHANG 上班，GOH 固定休息
FRI = date(2026, 10, 23)        # 两位都上班

PHANG_DAY = ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
             "13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "16:00", "16:30"]
GOH_DAY = ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30", "12:00", "12:30",
           "14:00", "14:30", "15:00", "15:30"]


class FakeGpis:
    """假的 GPiS：{(日期, 医生): [预约]}；记下读过哪几天。"""

    def __init__(self, book=None, fail=False):
        self.book = book or {}
        self.fail = fail
        self.reads: list[tuple[date, str]] = []

    def appointments_for(self, day, doctor_id):
        self.reads.append((day, doctor_id))
        if self.fail:
            raise RuntimeError("Login failed for user 'secret-user' (connection string with PWD=xyz)")
        return self.book.get((day, doctor_id), [])


def appt(i, slot, remarks="S+P", contact=1000):
    return GpisAppointment(i, slot, "Booked", contact + i, remarks)


@pytest.fixture
def db(session):
    seed(session)
    return session


def ctx_for(db, gpis=None):
    return ToolContext(session=db, gpis=gpis or FakeGpis(), today=TODAY)


# ---------- 检查 AI 给的参数 ----------

@pytest.mark.parametrize("value", ["明天", "22/10/2026", "", "2026-10-32"])
def test_date_that_is_not_a_date(db, value):
    out = ai_tools.check_available_slots(ctx_for(db), value, "S+P")
    assert set(out) == {"error"}
    assert "YYYY-MM-DD" in out["error"] and repr(value) in out["error"] and TODAY.isoformat() in out["error"]


@pytest.mark.parametrize("day", [TODAY, TODAY - timedelta(days=1)])
def test_today_and_past_dates_are_refused(db, day):
    out = ai_tools.check_available_slots(ctx_for(db), day.isoformat(), "S+P")
    assert "not after today" in out["error"]


def test_only_60_days_ahead(db):
    assert "times" in str(ai_tools.check_available_slots(ctx_for(db), (TODAY + timedelta(days=60)).isoformat(), "S+P"))
    out = ai_tools.check_available_slots(ctx_for(db), (TODAY + timedelta(days=61)).isoformat(), "S+P")
    assert "too far ahead" in out["error"]


def test_unknown_treatment_lists_the_codes_the_ai_can_book(db):
    out = ai_tools.check_available_slots(ctx_for(db), THU.isoformat(), "scaling")
    assert "Unknown treatment code 'scaling'" in out["error"]
    assert "S+P" in out["error"] and "OR" in out["error"]
    assert "RCT" not in out["error"]          # AI 不能约的不列出来


def test_lower_case_code_is_fine(db):
    out = ai_tools.check_available_slots(ctx_for(db), THU.isoformat(), " s+p ")
    assert out["service"] == "S+P"


@pytest.mark.parametrize("code", ["RCT", "XLA", "ISSUE CROWN"])
def test_treatments_staff_book_are_handed_over(db, code):
    out = ai_tools.check_available_slots(ctx_for(db), THU.isoformat(), code)
    assert "booked by staff" in out["error"] and "hand over to staff" in out["error"]


def test_treatment_that_may_need_one_hour_is_for_staff_even_if_ai_can_book(db):
    db.get(Service, "VENEER").ai_can_book = True        # 可能要 1 hour（D15）
    out = ai_tools.check_available_slots(ctx_for(db), THU.isoformat(), "VENEER")
    assert "booked by staff" in out["error"]


def test_inactive_treatment_is_unknown(db):
    db.get(Service, "F").active = False
    out = ai_tools.check_available_slots(ctx_for(db), THU.isoformat(), "F")
    assert "Unknown treatment code" in out["error"]


@pytest.mark.parametrize("value", ["PHANG", "phang", "Dr Phang", "DR. PHANG", " dr phang "])
def test_doctor_names_the_ai_may_use(db, value):
    out = ai_tools.check_available_slots(ctx_for(db), THU.isoformat(), "S+P", value)
    assert [d["doctor"] for d in out["doctors"]] == ["PHANG"]


def test_unknown_or_inactive_doctor(db):
    out = ai_tools.check_available_slots(ctx_for(db), THU.isoformat(), "S+P", "Dr Tan")
    assert "Unknown doctor 'Dr Tan'" in out["error"] and "PHANG" in out["error"] and "GOH" in out["error"]
    db.get(Doctor, "GOH").active = False
    out = ai_tools.check_available_slots(ctx_for(db), FRI.isoformat(), "S+P", "GOH")
    assert "Unknown doctor" in out["error"]


# ---------- check_available_slots ----------

def test_empty_day_gives_every_30_minute_time(db):
    out = ai_tools.check_available_slots(ctx_for(db), FRI.isoformat(), "S+P")
    assert out == {
        "date": "2026-10-23",
        "weekday": "Friday",
        "service": "S+P",
        "doctors": [
            {"doctor": "GOH", "name": "GOH", "times": GOH_DAY},
            {"doctor": "PHANG", "name": "PHANG", "times": PHANG_DAY},
        ],
    }


def test_doctor_who_does_not_work_that_day_is_not_read_from_gpis(db):
    gpis = FakeGpis()
    out = ai_tools.check_available_slots(ctx_for(db, gpis), THU.isoformat(), "S+P")
    goh = next(d for d in out["doctors"] if d["doctor"] == "GOH")
    assert goh == {"doctor": "GOH", "name": "GOH", "times": [], "not_available": "doctor not working this day"}
    assert gpis.reads == [(THU, "PHANG")]


def test_clinic_closed(db):
    db.add(ClinicClosure(closure_date=FRI, reason="Test holiday"))
    gpis = FakeGpis()
    out = ai_tools.check_available_slots(ctx_for(db, gpis), FRI.isoformat(), "S+P", "PHANG")
    assert out["doctors"][0]["not_available"] == "clinic closed (Test holiday)"
    assert gpis.reads == []


def test_full_slot_depends_on_the_treatment(db):
    # 10:00 已经 2 个人：S+P 能当第 3 人（W15），C/UP 不能
    gpis = FakeGpis({(THU, "PHANG"): [appt(1, "10:00"), appt(2, "10:00")]})
    sp = ai_tools.check_available_slots(ctx_for(db, gpis), THU.isoformat(), "S+P", "PHANG")
    cup = ai_tools.check_available_slots(ctx_for(db, gpis), THU.isoformat(), "C/UP", "PHANG")
    assert "10:00" in sp["doctors"][0]["times"]
    assert "10:00" not in cup["doctors"][0]["times"] and "10:30" in cup["doctors"][0]["times"]


def test_pending_requests_take_their_slot(db):
    # 10:00 GPiS 有 1 人 + 本系统 1 个 PENDING 的请求 = 2 人：C/UP 不能再约（A8）
    p = create_customer(db, "Test Patient", "0123456789")
    create_appointment_request(db, p, "S+P", doctor_id="PHANG", preferred_date=THU, preferred_slot=time(10))
    gpis = FakeGpis({(THU, "PHANG"): [appt(1, "10:00")]})
    out = ai_tools.check_available_slots(ctx_for(db, gpis), THU.isoformat(), "C/UP", "PHANG")
    assert "10:00" not in out["doctors"][0]["times"]


def test_day_staff_must_check_gives_no_times(db):
    # 诊所自己当联系人的记录（医生的私人安排）：AI 不推荐，转员工（D15）
    gpis = FakeGpis({(THU, "PHANG"): [GpisAppointment(1, "15:00", "Booked", 34094, "MEETING")]})
    out = ai_tools.check_available_slots(ctx_for(db, gpis), THU.isoformat(), "S+P", "PHANG")
    assert out["doctors"][0]["times"] == []
    assert "hand over to staff" in out["doctors"][0]["not_available"]


def test_fully_booked_day(db):
    full = [appt(i * 10 + n, t) for i, t in enumerate(PHANG_DAY) for n in range(3)]
    out = ai_tools.check_available_slots(ctx_for(db, FakeGpis({(THU, "PHANG"): full})), THU.isoformat(), "S+P", "PHANG")
    assert out["doctors"][0] == {"doctor": "PHANG", "name": "PHANG", "times": [], "not_available": "fully booked"}


def test_nothing_about_other_patients_goes_to_the_ai(db):
    gpis = FakeGpis({(THU, "PHANG"): [GpisAppointment(129667, "11:30", "Confirmed", 5555, "S+P SECRET REMARK")]})
    out = str(ai_tools.check_available_slots(ctx_for(db, gpis), THU.isoformat(), "S+P", "PHANG"))
    for leak in ("129667", "5555", "SECRET", "Confirmed", "booked", "remaining"):
        assert leak not in out


def test_gpis_failure_does_not_leak_the_connection_details(db, caplog):
    out = ai_tools.check_available_slots(ctx_for(db, FakeGpis(fail=True)), THU.isoformat(), "S+P")
    assert "cannot be read right now" in out["error"] and "hand over to staff" in out["error"]
    assert "secret-user" not in out["error"] and "PWD" not in out["error"]
    assert "AI 工具读 GPiS 失败" in caplog.text


# ---------- find_next_available ----------

def test_next_available_finds_three_days(db):
    out = ai_tools.find_next_available(ctx_for(db), "S+P", "GOH")
    # GOH 星期三、四休息：明天（四）没有 → 五、六、日
    assert [d["date"] for d in out["days"]] == ["2026-10-23", "2026-10-24", "2026-10-25"]
    assert out["days"][0] == {"date": "2026-10-23", "weekday": "Friday",
                              "doctors": [{"doctor": "GOH", "name": "GOH", "times": GOH_DAY}]}
    assert "message" not in out


def test_next_available_skips_closed_and_full_days(db):
    db.add(ClinicClosure(closure_date=FRI, reason="Test holiday"))
    full = [appt(i * 10 + n, t) for i, t in enumerate(PHANG_DAY) for n in range(3)]
    gpis = FakeGpis({(THU, "PHANG"): full})
    out = ai_tools.find_next_available(ctx_for(db, gpis), "S+P", "PHANG")
    assert [d["date"] for d in out["days"]] == ["2026-10-24", "2026-10-25", "2026-10-26"]
    assert (FRI, "PHANG") not in gpis.reads        # 休息日不用读 GPiS


def test_next_available_only_lists_doctors_with_time(db):
    out = ai_tools.find_next_available(ctx_for(db), "S+P")
    thu = out["days"][0]
    assert thu["date"] == "2026-10-22" and [d["doctor"] for d in thu["doctors"]] == ["PHANG"]


def test_next_available_from_a_date(db):
    out = ai_tools.find_next_available(ctx_for(db), "S+P", "PHANG", from_date="2026-11-02")
    assert out["days"][0]["date"] == "2026-11-02"
    # 过去的日子：从明天开始找
    out = ai_tools.find_next_available(ctx_for(db), "S+P", "PHANG", from_date="2026-01-01")
    assert out["days"][0]["date"] == "2026-10-22"
    assert "YYYY-MM-DD" in ai_tools.find_next_available(ctx_for(db), "S+P", from_date="next week")["error"]


def test_next_available_nothing_in_14_days(db):
    for n in range(1, 20):
        db.add(ClinicClosure(closure_date=TODAY + timedelta(days=n), reason="Test closure"))
    out = ai_tools.find_next_available(ctx_for(db), "S+P")
    assert out["days"] == [] and out["searched_until"] == "2026-11-04"
    assert "hand over to staff" in out["message"]


def test_next_available_stops_at_60_days(db):
    out = ai_tools.find_next_available(ctx_for(db), "S+P", from_date=(TODAY + timedelta(days=55)).isoformat())
    assert out["searched_until"] == (TODAY + timedelta(days=60)).isoformat()


def test_next_available_checks_the_treatment(db):
    assert "booked by staff" in ai_tools.find_next_available(ctx_for(db), "RCT")["error"]


def test_command_line_prints_what_the_ai_gets(db, monkeypatch, capsys):
    from contextlib import nullcontext

    monkeypatch.setattr("app.db.session.new_session", lambda: nullcontext(db))
    monkeypatch.setattr("app.main._default_reader", lambda: FakeGpis())
    monkeypatch.setattr("app.reminders.clinic_today", lambda: TODAY)
    assert ai_tools.main(["check", "2026-10-22", "S+P", "Dr Phang"]) == 0
    assert '"times": [' in capsys.readouterr().out
    assert ai_tools.main(["next", "S+P", "--from", "next week"]) == 1
    assert "YYYY-MM-DD" in capsys.readouterr().out
