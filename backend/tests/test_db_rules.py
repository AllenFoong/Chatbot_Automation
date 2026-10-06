"""诊所设置搬进 PostgreSQL：初始设置读出来要和 Phase 2 完全一样；数据库会拒绝错的设置。"""

from datetime import date, time

import pytest

from app.availability import check_available_slots
from app.db.models import ClinicClosure, ClinicSettings, Doctor, DoctorLeave, DoctorSchedule, Service
from app.db.rules import RulesNotConfigured, load_clinic_rules
from app.db.seed import seed
from tests.database import assert_rejected
from tests.rules import RULES

WED = date(2026, 9, 2)


def test_seeded_settings_equal_phase2_rules(session):
    """设置一样 → 同一天的 GPiS 预约算出来的空档和 Phase 2 一样。"""
    seed(session)
    assert load_clinic_rules(session) == RULES


def test_seed_twice_adds_nothing_and_keeps_staff_changes(session):
    assert seed(session) == {"doctors": 2, "doctor_schedules": 14, "services": 26, "clinic_settings": 1}
    session.get(ClinicSettings, 1).max_per_slot_for_ai = 2
    session.get(Service, "XLA").active = False
    session.flush()

    assert seed(session) == {}
    assert session.get(ClinicSettings, 1).max_per_slot_for_ai == 2
    assert session.get(Service, "XLA").active is False


def test_not_seeded_yet(session):
    with pytest.raises(RulesNotConfigured):
        load_clinic_rules(session)


def test_staff_changes_take_effect(session):
    seed(session)
    goh_wednesday = session.get(DoctorSchedule, ("GOH", 3))
    goh_wednesday.is_working, goh_wednesday.start_time, goh_wednesday.last_slot = True, time(9), time(11, 30)
    session.add_all([
        ClinicClosure(closure_date=date(2026, 12, 25), reason="Christmas"),
        DoctorLeave(doctor_id="GOH", leave_date=date(2026, 10, 10)),
    ])
    session.get(Doctor, "PHANG").active = False
    session.flush()

    rules = load_clinic_rules(session)
    r = check_available_slots(WED, "GOH", "S+P", [], rules)
    assert r.day_status == "OK"
    assert [s.time for s in r.slots if s.can_30] == ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30"]
    assert check_available_slots(date(2026, 12, 25), "GOH", "S+P", [], rules).day_status == "CLINIC_CLOSED"
    assert check_available_slots(date(2026, 10, 10), "GOH", "S+P", [], rules).day_status == "DOCTOR_ON_LEAVE"
    assert check_available_slots(WED, "PHANG", "S+P", [], rules).day_status == "UNKNOWN_DOCTOR"   # 离职


@pytest.mark.parametrize("hours", [
    dict(weekday=8, is_working=False),                                                   # 没有星期八
    dict(weekday=1, is_working=True),                                                    # 上班但没写时间
    dict(weekday=1, is_working=True, start_time=time(17), last_slot=time(9)),            # 开始比最后一格晚
    dict(weekday=1, is_working=True, start_time=time(9, 15), last_slot=time(16, 30)),    # 不在 30 分钟的格上
    dict(weekday=1, is_working=True, start_time=time(9), last_slot=time(16, 30),
         break_start=time(12)),                                                          # 只有午休开始
    dict(weekday=1, is_working=True, start_time=time(9), last_slot=time(16, 30),
         break_start=time(13), break_end=time(12)),                                      # 午休结束比开始早
])
def test_bad_schedule_is_rejected(session, hours):
    session.add(Doctor(id="TEST", display_name="Test doctor"))
    session.flush()
    assert_rejected(session, DoctorSchedule(doctor_id="TEST", **hours))


def test_bad_codes_and_settings_are_rejected(session):
    assert_rejected(session, Service(code="s+p", name="lower case"))
    assert_rejected(session, Doctor(id="GOH ", display_name="trailing space"))
    assert_rejected(session, ClinicSettings(id=2, clinic_contact_id=1))                  # 只能有一行
    assert_rejected(session, ClinicSettings(id=1, max_per_slot=4, clinic_contact_id=1))  # 每格最多 3 人（W22）
