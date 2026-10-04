"""空档计算测试：用假数据重现 sql/README.md 的 T1–T11。不连接任何数据库。"""

from datetime import date
from itertools import count

import pytest

from app.availability import GpisAppointment, check_available_slots, duration_slots, normalize_remarks
from app.clinic_rules import DEFAULT_RULES, ClinicRules

TUE, WED, THU, FRI = date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4)
CLINIC = DEFAULT_RULES.clinic_contact_id
_ids = count(1)


def appt(slot, remarks="S+P", status="Booked", contact_id=1):
    return GpisAppointment(next(_ids), slot, status, contact_id, remarks)


def run(day, doctor, appts=(), service="S+P", rules=DEFAULT_RULES):
    return check_available_slots(day, doctor, service, list(appts), rules)


def slot(result, hhmm):
    return next(s for s in result.slots if s.time == hhmm)


# ---------- 排班 ----------

def test_t1_phang_tuesday_not_working():
    r = run(TUE, "PHANG", [appt("00:00", "REMIND")] * 3)
    assert r.day_status == "DOCTOR_NOT_WORKING"
    assert r.slots == []
    assert r.patients == 0


def test_t2_goh_wednesday_and_thursday_not_working():
    assert run(WED, "GOH").day_status == "DOCTOR_NOT_WORKING"
    assert run(THU, "GOH").day_status == "DOCTOR_NOT_WORKING"


def test_t3_phang_normal_day_grid():
    r = run(THU, "PHANG")
    assert r.day_status == "OK"
    assert [s.time for s in r.slots][0] == "09:00"
    assert r.slots[-1].time == "17:00" and r.slots[-1].kind == "AFTER HOURS"
    assert [s.time for s in r.slots if s.kind == "BREAK"] == ["12:00", "12:30"]
    assert sum(1 for s in r.slots if s.can_30) == 14
    assert slot(r, "16:30").can_60          # 最后一格可以开始 1 hour


def test_t4_goh_tuesday_lunch_at_12():
    r = run(TUE, "GOH")
    assert [s.time for s in r.slots if s.kind == "BREAK"] == ["12:00", "12:30"]
    assert slot(r, "13:00").can_30
    assert slot(r, "15:30").can_60          # W27
    assert sum(1 for s in r.slots if s.can_30) == 12


def test_t5_goh_weekday_lunch_at_13():
    r = run(FRI, "GOH")
    assert [s.time for s in r.slots if s.kind == "BREAK"] == ["13:00", "13:30"]
    assert r.slots[-1].time == "16:00" and r.slots[-1].kind == "AFTER HOURS"
    assert sum(1 for s in r.slots if s.can_30) == 12


def test_t11_one_hour_cannot_run_into_lunch():
    assert not slot(run(THU, "PHANG"), "11:30").can_60
    assert not slot(run(FRI, "GOH"), "12:30").can_60
    assert slot(run(FRI, "GOH"), "12:00").can_60


# ---------- 每格上限 ----------

def test_t6_full_slot_and_neighbour_cap():
    r = run(WED, "PHANG", [appt("09:30")] * 3)
    assert slot(r, "09:30").remaining == 0 and not slot(r, "09:30").can_30
    assert slot(r, "09:00").cap == 2
    assert slot(r, "10:00").cap == 2
    assert slot(r, "10:30").cap == 3


def test_t6_two_booked_third_place_only_for_some_services():
    two = [appt("10:00"), appt("10:00")]
    assert slot(run(WED, "PHANG", two, service="S+P"), "10:00").can_30
    assert slot(run(WED, "PHANG", two, service="retainer"), "10:00").can_30
    assert not slot(run(WED, "PHANG", two, service="C/UP"), "10:00").can_30


def test_t7_non_third_service_caps_at_two():
    r = run(WED, "PHANG", service="C/UP")
    assert {s.cap for s in r.slots if s.cap is not None} == {2}


def test_max_per_slot_for_ai_setting():
    rules = ClinicRules(**{**DEFAULT_RULES.__dict__, "max_per_slot_for_ai": 2})
    r = run(WED, "PHANG", service="S+P", rules=rules)
    assert {s.cap for s in r.slots if s.cap is not None} == {2}


def test_four_in_one_slot_counts_as_full():
    r = run(WED, "PHANG", [appt("14:00")] * 4)
    assert slot(r, "14:00").booked == 4 and slot(r, "14:00").remaining == 0


# ---------- 长预约 ----------

def test_t8_one_hour_blocks_two_slots():
    r = run(WED, "PHANG", [appt("16:00", "RCT 1 hour")])
    assert r.appointments[0].dur_slots == 2
    for t in ("16:00", "16:30"):
        assert slot(r, t).kind == "LONG APPT"
        assert slot(r, t).remaining == 0 and slot(r, t).cap is None
    assert not slot(r, "15:30").can_60      # 下一格被占
    assert slot(r, "15:30").can_30


@pytest.mark.parametrize("remarks,expected", [
    ("1 HOUR", 2), ("1HR", 2), ("SCALING (1H)", 2),
    ("1.5 HOUR", 3), ("1.30HOUR", 3), ("1 HOUR 30", 3), ("1HR30", 3),
    ("2 HOURS", 4), ("2HR", 4),
    ("20MIN", 1), ("45 MIN", 1), ("S+P", 1), ("", 1),
])
def test_duration_patterns(remarks, expected):
    assert duration_slots(normalize_remarks(remarks)) == expected


def test_one_and_half_hour_blocks_three_slots():
    r = run(WED, "PHANG", [appt("09:00", "*1.5 hour*")])
    assert [s.time for s in r.slots if s.kind == "LONG APPT"] == ["09:00", "09:30", "10:00"]


# ---------- 不占时段的记录 ----------

def test_reminders_cancelled_and_postponed_are_ignored():
    r = run(WED, "PHANG", [
        appt("00:00", "REMIND"),
        appt("10:00", status="Canceled"),
        appt("10:00", status="Postpone"),
        appt("10:00"),
    ])
    assert r.patients == 1
    assert slot(r, "10:00").booked == 1
    assert len(r.appointments) == 2         # Canceled / Postpone 不读


def test_t9_off_day_on_reminder_record():
    r = run(FRI, "GOH", [appt("00:00", "Dr Goh off day"), appt("10:00")])
    assert r.day_status == "OFFDAY_IN_GPIS"
    assert all(s.remaining == 0 and not s.can_30 for s in r.slots)


def test_off_sunday_is_not_off_day():
    assert run(FRI, "GOH", [appt("00:00", "OFF SUNDAY")]).day_status == "OK"


def test_t10_clinic_placeholder_needs_review_and_not_counted():
    r = run(WED, "PHANG", [appt("11:00", "", contact_id=CLINIC), appt("09:00")])
    assert r.day_status == "NEEDS_REVIEW" and not r.bookable
    assert r.patients == 1
    assert slot(r, "11:00").booked == 0
    assert slot(r, "11:00").can_30          # 空档照算，只是转员工


def test_unparsed_hour_needs_review():
    assert run(WED, "PHANG", [appt("10:00", "3 HOUR?")]).day_status == "NEEDS_REVIEW"
    assert run(WED, "PHANG", [appt("10:00", "2.5HR")]).day_status == "NEEDS_REVIEW"
    assert run(WED, "PHANG", [appt("00:00", "HOUR")]).day_status == "OK"     # 00:00 不算


# ---------- 设置 ----------

def test_closure_and_leave():
    rules = ClinicRules(**{
        **DEFAULT_RULES.__dict__,
        "closures": {WED: "Public holiday"},
        "doctor_leaves": frozenset({("GOH", FRI)}),
    })
    r = run(WED, "PHANG", rules=rules)
    assert r.day_status == "CLINIC_CLOSED" and r.note == "Public holiday"
    assert all(s.remaining == 0 for s in r.slots)
    assert run(FRI, "GOH", rules=rules).day_status == "DOCTOR_ON_LEAVE"


def test_unknown_doctor_and_case_insensitive_input():
    assert run(WED, "CHER").day_status == "UNKNOWN_DOCTOR"
    assert run(WED, " phang ", service="s+p").day_status == "OK"
