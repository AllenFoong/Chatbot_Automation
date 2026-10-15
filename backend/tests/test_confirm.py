"""员工确认时给点选的 GPiS 名单、确认消息（app/confirm.py）。假名字，不连数据库。"""

from datetime import date, time

from app.confirm import GpisChoice, RequestFacts, gpis_choices, may_send, rank, render_confirmation
from app.reminder_demo import DemoReminderSource
from app.reminders import ReminderAppointment, ReminderText

FRI = date(2026, 10, 9)
CLINIC = 34094


def row(i, slot="16:00", doctor="PHANG", status="Confirmed", contact=5000, name="DEMO KID B (P)", remarks="S+P"):
    return ReminderAppointment(i, FRI, slot, doctor, status, contact, name, "0120000001", remarks)


def test_only_real_patient_appointments_are_listed():
    rows = [
        row(1),
        row(2, status="Canceled"),
        row(3, status="Postpone"),
        row(4, slot="00:00", remarks="REMIND PT"),
        row(5, contact=CLINIC),
        row(6, remarks="OFF DAY"),
        row(7, slot="1000"),          # 看不懂的时段：员工自己处理
        row(1),                       # 视图里同一个预约有几行
        row(8, slot="09:30", doctor=" goh ", status=None, name=None),
    ]
    choices = gpis_choices(rows, CLINIC)
    assert [c.appointment_id for c in choices] == [1, 8]
    assert choices[0] == GpisChoice(1, FRI, time(16), "PHANG", "DEMO KID B", 5000)
    assert choices[1].doctor_id == "GOH" and choices[1].patient_name == ""


def test_same_patient_first_then_doctor_then_time():
    choices = gpis_choices([
        row(1, slot="09:00", doctor="GOH", contact=1),
        row(2, slot="16:00", doctor="GOH", contact=2),
        row(3, slot="10:00", doctor="PHANG", contact=3),
        row(4, slot="16:00", doctor="PHANG", contact=4),
        row(5, slot="11:00", doctor="GOH", contact=9),
    ], CLINIC)
    facts = RequestFacts(contact_id=9, doctor_id="phang", slot=time(16))
    assert [c.appointment_id for c in rank(choices, facts)] == [5, 4, 3, 2, 1]
    assert [c.appointment_id for c in rank(choices, RequestFacts(None, None, None))] == [1, 3, 5, 2, 4]


def test_only_production_or_fake_data_may_send():
    class Gpis:
        def __init__(self, production):
            self.is_production = production

    assert may_send(Gpis(True))
    assert not may_send(Gpis(False))                 # GPiS_Dev：真的病人名字
    assert may_send(DemoReminderSource("60120000001"))


def test_confirmation_uses_gpis_values():
    c = GpisChoice(1, FRI, time(16, 30), "PHANG", "DEMO KID B", 5000)
    text = render_confirmation(c, "Phang", ReminderText("诊所", "Clinic", "Branch"))
    assert "NAME: DEMO KID B" in text and "DATE: 09/10/26" in text and "TIME: 4:30 PM" in text
    assert "DOCTOR: DR PHANG" in text and "BRANCH：Branch" in text
    assert "你好 这里是诊所" in text and "Hello, we are Clinic" in text
