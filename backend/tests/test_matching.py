"""PENDING 的请求对不对得上 GPiS 的预约（D70）。全部是假资料，不连数据库。"""

from datetime import date, time

import pytest

from app.availability import PendingHold, check_available_slots
from app.matching import BookedAppointment, RequestToMatch, find_matches, render_confirmation
from app.reminders import ReminderText
from tests.rules import RULES

DAY = date(2026, 10, 21)
CLINIC = RULES.clinic_contact_id


def req(rid=1, contact=501, day=DAY, slot=time(10, 0), doctor="PHANG"):
    return RequestToMatch(rid, contact, day, slot, doctor)


def appt(aid=9001, contact=501, day=DAY, slot="10:00", doctor="PHANG", status="Confirmed", remarks="S+P (P)"):
    return BookedAppointment(aid, day, slot, doctor, status, contact, remarks)


def test_same_patient_day_slot_and_doctor_match():
    assert find_matches([req()], [appt()], CLINIC) == {1: 9001}
    # GPiS 的医生代号有空格、小写也一样
    assert find_matches([req()], [appt(doctor=" phang ")], CLINIC) == {1: 9001}


@pytest.mark.parametrize("other", [
    appt(contact=502),                  # 别的病人（例：同一个号码的家人）
    appt(day=date(2026, 10, 22)),       # 别的日子
    appt(slot="10:30"),                 # 员工约成别的时间 → 员工自己按
    appt(doctor="GOH"),                 # 别的医生
    appt(status="Canceled"),
    appt(status="postpone"),
    appt(slot="00:00"),                 # 00:00 是提醒，不是预约
    appt(remarks="OFF DAY"),
])
def test_anything_different_does_not_match(other):
    assert find_matches([req()], [other], CLINIC) == {}


def test_one_appointment_matches_only_one_request():
    """同一位病人重复请求：两个都对得上同一个预约 → 都不自动，留给员工。"""
    assert find_matches([req(1), req(2)], [appt()], CLINIC) == {}


def test_two_appointments_for_one_request_are_left_to_staff():
    """GPiS 里同一格有两个这位病人的预约（输入了两次）→ 不知道是哪一个。"""
    assert find_matches([req()], [appt(9001), appt(9002)], CLINIC) == {}


def test_appointment_already_linked_to_another_request_is_not_used():
    assert find_matches([req()], [appt()], CLINIC, already_linked={9001}) == {}


def test_each_request_gets_its_own_appointment():
    """家人同一格（不同 ContactID）各对各的。"""
    found = find_matches([req(1, 501), req(2, 502)], [appt(9001, 501), appt(9002, 502)], CLINIC)
    assert found == {1: 9001, 2: 9002}


def test_pending_hold_counts_like_a_gpis_booking():
    """A8：PENDING 的请求和 GPiS 的预约一起算人数；1 hour 的占 2 格。"""
    wed = date(2026, 9, 2)
    plain = check_available_slots(wed, "PHANG", "C/UP", [], RULES)
    held = check_available_slots(wed, "PHANG", "C/UP", [], RULES,
                                 [PendingHold(1, time(10, 0)), PendingHold(2, time(10, 0)),
                                  PendingHold(3, time(15, 0), 60)])
    before = {s.time: s for s in plain.slots}
    after = {s.time: s for s in held.slots}
    assert before["10:00"].can_30 and not after["10:00"].can_30       # C/UP 一格最多 2 人
    assert after["10:00"].booked == 2 and held.pending == 3 and held.patients == 0
    assert after["15:00"].booked == 1 and after["15:30"].kind == "LONG APPT"
    assert before["14:30"].can_60 and not after["14:30"].can_60       # 下一格有人了


def test_confirmation_uses_the_booking_details():
    text = ReminderText(clinic_name="<诊所名>", clinic_name_en="<Clinic>", branch="<分行>")
    body = render_confirmation("Demo Patient (P)", DAY, time(14, 30), "Phang", text)
    assert "NAME: DEMO PATIENT\n" in body
    assert "DATE: 21/10/26 (Wed)" in body and "TIME: 2:30 PM" in body and "DOCTOR: DR PHANG" in body
    assert "<诊所名>" in body and "<Clinic>" in body and "<分行>" in body
