"""提醒名单（app/reminders.py）：全部是假名字、假号码。规则见 docs/architecture.md 8.3、D41、D49–D51。"""

from collections import namedtuple
from dataclasses import replace
from datetime import date

import pytest

from app.gpis import GpisReader, missing_columns
from app.reminder_demo import DemoReminderSource
from app.reminders import (
    PhoneKind, ReminderAppointment, ReminderText, build_reminder_list, clinic_today, lab_work_not_arrived,
    phone_kind, reminder_dates,
)
from app.reminders_cli import summary
from tests.rules import RULES

FRI = date(2026, 10, 9)        # PHANG、GOH 都上班
NAMES = {"PHANG": "PHANG", "GOH": "GOH"}
_next_id = iter(range(1, 10_000))


def appt(time_slot="10:00", doctor="PHANG", status="Confirmed", name="Demo Patient A", phone="012-000 0001",
         remarks="S+P (P)", day=FRI, contact_id=None, appointment_id=None) -> ReminderAppointment:
    i = appointment_id or next(_next_id)
    return ReminderAppointment(i, day, time_slot, doctor, status, contact_id or 5000 + i, name, phone, remarks)


def build(*rows, dates=(FRI,), rules=RULES, **kwargs):
    return build_reminder_list(list(dates), list(rows), rules, NAMES, **kwargs)


def only_group(result):
    groups = result.ready + result.needs_staff
    assert len(groups) == 1, groups
    return groups[0]


# ---------- 哪几天 ----------

def test_reminder_dates_is_tomorrow_on_a_normal_day():
    assert reminder_dates(date(2026, 10, 8), {}) == [FRI]


def test_reminder_dates_before_holidays_include_the_next_open_day():
    holidays = {date(2026, 10, 9): "Holiday", date(2026, 10, 10): "Holiday"}
    assert reminder_dates(date(2026, 10, 8), holidays) == [FRI, date(2026, 10, 10), date(2026, 10, 11)]


def test_clinic_today_uses_malaysia_time():
    from datetime import datetime, timezone
    assert clinic_today(datetime(2026, 10, 8, 16, 30, tzinfo=timezone.utc)) == date(2026, 10, 9)   # 00:30 MYT
    assert clinic_today(datetime(2026, 10, 8, 15, 59, tzinfo=timezone.utc)) == date(2026, 10, 8)


# ---------- 不是预约（只算数量） ----------

def test_cancelled_offday_and_todo_records_are_only_counted():
    r = build(
        appt(status="Canceled"), appt(status="Postpone"),
        appt("00:00", remarks="REMIND PT STO"),
        appt("00:00", doctor="GOH", remarks="OFF DAY !!!", name="Someone"),
    )
    assert r.ready == () and r.needs_staff == ()
    assert dict(r.not_appointments) == {"Cancelled or postponed": 2, "To-do at 00:00": 1, "OFF DAY record": 1}


# ---------- 要员工看 ----------

@pytest.mark.parametrize("row, problem", [
    (appt(contact_id=34094, name="CLINIC"), "Booked under the clinic's own contact"),
    (appt(status="Waiting"), "Status is Waiting"),
    (appt(status=None), "Status is empty"),
    (appt(doctor="CHER"), "CHER is not an active doctor"),
    (appt(day=date(2026, 10, 13)), "Dr PHANG does not work on Tuesday"),
    (appt("02:30"), "Time is outside working hours"),
    (appt("08:30"), "Time is outside working hours"),
    (appt("9:00"), "Unreadable time slot"),
    (appt(name="  "), "No patient name in GPiS"),
    (appt(name="(P)"), "No patient name in GPiS"),
    (appt(remarks="ISSUE CROWN 36 (P)"), "Lab work not marked as arrived (*C)"),
    (appt(phone=None), "No mobile number in GPiS"),
    (appt(phone="07-123 4567"), "Not a mobile number"),
])
def test_needs_staff(row, problem):
    r = build(row, dates=(row.appointment_date,))
    assert r.ready == ()
    assert problem in only_group(r).problems


def test_closure_and_leave_need_staff():
    rules = replace(RULES, closures={FRI: "Deepavali"}, doctor_leaves=frozenset({("GOH", FRI)}))
    r = build(appt(), appt(doctor="GOH", phone="012-000 0002"), rules=rules)
    problems = [g.problems for g in r.needs_staff]
    assert ("Clinic is closed that day (Deepavali)",) in problems
    assert any("Dr GOH is on leave" in p for p in problems)


def test_offday_in_gpis_makes_that_doctors_patients_need_staff():
    r = build(appt("00:00", doctor="GOH", remarks="DR GOH OFF DAY"), appt(doctor="GOH"), appt(phone="012-000 0002"))
    assert [g.lines[0].doctor_id for g in r.ready] == ["PHANG"]
    assert r.needs_staff[0].problems == ("GPiS has an OFF DAY record for Dr GOH",)


@pytest.mark.parametrize("time_slot", ["12:00", "12:30", "17:00", "16:30"])
def test_lunch_break_and_after_hours_exceptions_are_still_reminded(time_slot):
    """员工破例排的（午休、下班后一格）是真的预约（clinic-workflow.md 第 1 节）。"""
    assert len(build(appt(time_slot)).ready) == 1


def test_closed_status_is_not_an_appointment():
    """病人提前来了，员工改成 Closed：不提醒，只算数量（D76）。"""
    r = build(appt(status="Closed"))
    assert not r.ready and not r.needs_staff
    assert dict(r.not_appointments) == {"Closed (patient already came)": 1}


# ---------- *C（D50、D51） ----------

@pytest.mark.parametrize("remarks, not_arrived", [
    ("ISSUE CROWN 36 (P)", True),
    ("ISSUE CROWN 36 (P) *C", False),
    ("ISSUE C 36 *C", False),
    ("ISSUE C36", True),
    ("ISSUE B 33-37 (P)", True),
    ("ISSUE BRIDGE *C", False),
    ("ISSUE IMPLANT 46", True),
    ("ISSUE DENTURE *C", False),
    ("ISSUE D(P)", True),            # ISSUE D = ISSUE DENTURE（D77）
    ("ISSUE D (P) *C", False),
    ("C/UP AFTER ISSUE D(P)", False),
    ("ISSUE DR CHECK", False),       # D 后面接字母不算
    ("MMR (P)", True),
    ("TRY-IN (G) *C", False),
    ("TRY IN", True),
    ("VENEER 11 21", True),
    ("VENEERS *C", False),
    ("*C ISSUE CROWN", True),        # *C 要在代码后面
    ("ISSUE CROWN *c", True),        # 一定是大写 *C（W47）
    ("ISSUE CROWN *CROWN", True),
    ("SOFT TISSUE CHECK", False),    # TISSUE 不是 ISSUE
    ("RCT (C) 36,SC 36 (P)", False), # (C) 是以前的医生，不是 *C
    ("S+P", False),
    ("C/UP AFTER ISSUE DENTURE (P)", False),     # 装好之后的复诊（D57）
    ("c/up after  issue crown 36", False),
    ("C/UP AFTER ISSUE CROWN 36, ISSUE BRIDGE 44 (P)", True),   # 后面还有一个真的要戴的
    ("ISSUE DENTURE AFTER XLA", True),           # AFTER 在代码后面不算
    (None, False),
])
def test_lab_work_needs_star_c(remarks, not_arrived):
    assert lab_work_not_arrived(remarks) is not_arrived


# ---------- 号码 ----------

@pytest.mark.parametrize("phone, kind", [
    ("60123456789", PhoneKind.MY_MOBILE),
    ("6071234567", PhoneKind.LANDLINE),
    ("6591234567", PhoneKind.SG_MOBILE),
    ("6581234567", PhoneKind.SG_MOBILE),
    ("6561234567", PhoneKind.LANDLINE),
    ("447700900123", PhoneKind.OTHER_COUNTRY),
    (None, PhoneKind.MISSING),
])
def test_phone_kind(phone, kind):
    assert phone_kind(phone) is kind


def test_unreadable_phone_is_missing():
    assert only_group(build(appt(phone=":01"))).phone_kind is PhoneKind.MISSING


# ---------- 合成一条（D49）、消息 ----------

def test_family_on_one_number_gets_one_message():
    r = build(
        appt("10:30", doctor="GOH", name="Demo Patient B", phone="+60 12-000 0001"),
        appt("10:00", name="demo  patient a", phone="012-0000001"),
    )
    g = only_group(r)
    assert g.ready and g.phone == "60120000001"
    assert [ln.patient_name for ln in g.lines] == ["DEMO PATIENT A", "DEMO PATIENT B"]   # 照时间排
    assert "NAME: DEMO PATIENT A & DEMO PATIENT B\n" in g.message
    assert "TIME: 10:00 AM & 10:30 AM\n" in g.message
    assert "DOCTOR: DR PHANG & DR GOH\n" in g.message
    assert "DATE: 09/10/26\n" in g.message


def test_same_time_and_doctor_are_written_once():
    g = only_group(build(appt("13:00", name="Demo A"), appt("13:00", name="Demo B")))
    assert "NAME: DEMO A & DEMO B\nDATE: 09/10/26\nTIME: 1:00 PM\nDOCTOR: DR PHANG\n" in g.message


def test_p_and_g_after_the_name_are_not_sent():
    """GPiS 的名字后面的 (P)、(G) 不是名字的一部分（D56）；名字中间的括号不动。"""
    g = only_group(build(
        appt("10:00", name="Demo Patient A(P)"),
        appt("10:30", doctor="GOH", name="demo patient b ( g )"),
        appt("11:00", name="Demo (Ah) C (P)(G)"),
    ))
    assert [ln.patient_name for ln in g.lines] == ["DEMO PATIENT A", "DEMO PATIENT B", "DEMO (AH) C"]
    assert "NAME: DEMO PATIENT A & DEMO PATIENT B & DEMO (AH) C\n" in g.message


def test_message_uses_the_clinic_names_from_settings():
    text = ReminderText(clinic_name="诊所甲", clinic_name_en="Demo Dental", branch="Demo Branch")
    g = only_group(build(appt("12:00"), text=text))
    assert "这里是诊所甲 🦷" in g.message and "BRANCH：Demo Branch" in g.message
    assert "we are Demo Dental" in g.message and "TIME: 12:00 PM" in g.message
    assert "tomorrow" not in g.message.lower()          # 假期前要提早发（W45）


def test_duplicate_records_of_one_patient_become_one_line():
    same = dict(contact_id=777, name="Demo A")
    g = only_group(build(appt(**same, appointment_id=1001), appt(**same, appointment_id=1002)))
    assert [ln.appointment_ids for ln in g.lines] == [(1001, 1002)]


def test_same_appointment_from_the_view_is_read_once():
    row = appt(appointment_id=2001)
    assert len(only_group(build(row, row)).lines) == 1


def test_one_family_member_with_a_problem_sends_the_whole_number_to_staff():
    r = build(appt(name="Demo A"), appt("10:30", name="Demo B", remarks="ISSUE CROWN 36"))
    g = only_group(r)
    assert not g.ready and len(g.lines) == 2
    assert g.problems == ("Lab work not marked as arrived (*C)",)


def test_more_than_five_on_one_number_needs_staff():
    rows = [appt(f"{9 + i}:00".zfill(5), name=f"Demo {i}") for i in range(6) if i != 3]
    rows += [appt("14:00", name="Demo X")]
    g = only_group(build(*rows))
    assert "More than 5 appointments on one number" in g.problems


def test_same_number_on_two_dates_gets_two_messages():
    sat = date(2026, 10, 10)
    r = build(appt(), appt(day=sat), dates=(FRI, sat))
    assert [g.day for g in r.ready] == [FRI, sat]


def test_opted_out_number_is_not_sent():
    g = only_group(build(appt(), opted_out=frozenset({"60120000001"})))
    assert g.problems == ("Opted out of reminders",)


def test_other_dates_are_ignored():
    assert build(appt(day=date(2026, 10, 10))).ready == ()


def test_landline_has_no_message():
    assert only_group(build(appt(phone="07-123 4567"))).message is None


# ---------- 终端的摘要没有病人资料（D44） ----------

def test_cli_summary_has_no_names_phones_or_remarks():
    r = build(
        appt(name="Secret Name One", phone="012-345 6789", remarks="SECRET REMARK"),
        appt("11:00", name="Secret Name Two", phone="07-111 2222", remarks="ISSUE CROWN SECRET"),
    )
    text = "\n".join(summary(r, "GPiS_Dev"))
    for secret in ("SECRET", "Secret", "6789", "3456", "1112222", "0123"):
        assert secret not in text
    assert "#1" in text and "#2" in text and "Lab work not marked as arrived" in text


# ---------- GPiS（不连真的数据库） ----------

Row = namedtuple("Row", "AppointmentID AppointmentDate TimeSlot DoctorID Status ContactID ContactName Remarks HPNo")


def test_reader_keeps_one_row_per_appointment(monkeypatch):
    from datetime import datetime
    reader = GpisReader("DRIVER=x", "GPiS_Dev")
    rows = [
        Row(1, datetime(2026, 10, 9), "10:00", "PHANG", "Confirmed", 5, "Demo", "S+P", None),
        Row(1, datetime(2026, 10, 9), "10:00", "PHANG", "Confirmed", 5, "Demo", "S+P", "012-000 0001"),
        Row(1, datetime(2026, 10, 9), "10:00", "PHANG", "Confirmed", 5, "Demo", "S+P", "012-000 0009"),
    ]
    monkeypatch.setattr(reader, "_query", lambda sql, *params: rows)
    [a] = reader.reminder_appointments(FRI, FRI)
    assert a.appointment_date == FRI and a.hp_no == "012-000 0001"
    assert reader.is_production is False and GpisReader("x", "GPiS").is_production is True


def test_missing_columns_ignores_case():
    found = {("tbl_cah_appointment", c) for c in
             ("AppointmentID", "AppointmentDate", "TimeSlot", "DoctorID", "Status", "ContactID", "ContactName",
              "Remarks")}
    assert missing_columns(found | {("Qry_CAH_Appointment", "APPOINTMENTID")}) == ["Qry_CAH_Appointment.HPNo"]


def test_demo_source_uses_only_fake_names():
    rows = DemoReminderSource("60199999999").reminder_appointments(FRI, date(2026, 10, 10))
    assert len(rows) == 16 and all(r.contact_name.startswith("Demo Patient") for r in rows)
    assert {r.hp_no for r in rows if r.contact_name in ("Demo Patient A", "Demo Patient B")} == {"60199999999"}
