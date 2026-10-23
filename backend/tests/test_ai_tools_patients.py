"""6a-3b：AI 找病人、原来的医生、建请求（全部是假名字、假号码）。"""

from datetime import date, time

import pytest
from sqlalchemy import func, select

from app import ai_tools
from app.ai_tools import HIDDEN_NAME, ToolContext
from app.db import conversations as conv
from app.db.customers import create_customer
from app.db.models import AppointmentRequest, Customer, Doctor, RequestStatus
from app.db.seed import seed
from app.gpis import GpisPatient, PastVisit, patients_from_rows
from app.reminder_demo import DemoReminderSource
from tests.test_ai_tools import FakeGpis, appt

TODAY = date(2026, 10, 21)
FRI = date(2026, 10, 23)
PHONE = "60120000001"
OTHER_PHONE = "60120000002"


class FakePatients:
    """假的 GPiS 病人：{号码: [病人]}、{ContactID: [预约]}。fake_data = 名字是假的，可以给 AI。"""

    is_production = False

    def __init__(self, by_phone=None, visits=None, fake_data=True):
        self.by_phone = by_phone or {}
        self.visits = visits or {}
        self.fake_data = fake_data

    def patients_for_phone(self, phone):
        return self.by_phone.get(phone, [])

    def visits_of(self, contact_id, first, last):
        return [v for v in self.visits.get(contact_id, []) if first <= v.day <= last]


FAMILY = FakePatients(
    # 和 patients_from_rows 一样，最近来过的在前
    by_phone={PHONE: [GpisPatient(34094, "THE CLINIC", date(2026, 10, 2)), GpisPatient(502, "DEMO KID", date(2026, 10, 1)),
                      GpisPatient(501, "DEMO MUM (P)", date(2026, 9, 1))],
              OTHER_PHONE: [GpisPatient(777, "SOMEONE ELSE", date(2026, 10, 1))]},
    visits={
        502: [PastVisit(date(2025, 6, 1), "PHANG", "Confirmed", "ON (P)"),
              PastVisit(date(2026, 9, 20), "GOH", "Confirmed", "OR (G) WITH"),
              PastVisit(date(2026, 10, 5), "PHANG", "Canceled", "OR (P)"),       # 取消的不算
              PastVisit(date(2026, 10, 10), "PHANG", "Confirmed", "S+P (P)"),    # 不是同一类疗程
              PastVisit(date(2026, 11, 20), "PHANG", "Confirmed", "OR (P)")],    # 以后的不看
    },
)


@pytest.fixture
def db(session):
    seed(session)
    return session


@pytest.fixture
def conversation(db):
    c = conv.open_conversation(db, conv.get_or_create_wa_contact(db, PHONE))
    db.commit()
    return c


def ctx_for(db, conversation=None, patients=FAMILY, gpis=None, phone=None):
    return ToolContext(session=db, gpis=gpis or FakeGpis(), today=TODAY, patients=patients,
                       conversation=conversation, phone=phone)


def requests(db):
    return list(db.scalars(select(AppointmentRequest).order_by(AppointmentRequest.id)))


# ---------- GPiS 的号码怎么比对 ----------

def test_gpis_phone_formats_match_the_whatsapp_number():
    rows = [
        (501, "DEMO MUM", date(2025, 1, 1), "012-000 0001"),
        (501, "DEMO MUM NEW NAME", date(2026, 9, 1), "+60 12-000 0001"),
        (502, "DEMO KID", date(2026, 10, 1), "0120000001"),
        (503, "NOT THIS ONE", date(2026, 10, 1), "+65 1200 0001"),     # 最后 8 位一样、国家不一样
        (504, "TWO NUMBERS", date(2026, 10, 1), "012-000 0001 / 016-111 2222"),
        (None, "NO CONTACT", date(2026, 10, 1), "012-000 0001"),
    ]
    assert patients_from_rows(rows, PHONE) == [
        GpisPatient(502, "DEMO KID", date(2026, 10, 1)),
        GpisPatient(501, "DEMO MUM NEW NAME", date(2026, 9, 1)),
    ]


def test_demo_source_has_a_family_on_your_own_phone():
    demo = DemoReminderSource(PHONE)
    assert [p.name for p in demo.patients_for_phone(PHONE)] == ["Demo Patient A", "Demo Patient B"]
    b = demo.patients_for_phone(PHONE)[1]
    assert any("OR" in (v.remarks or "") for v in demo.visits_of(b.contact_id, date.today().replace(day=1), date.today()))


# ---------- find_patients ----------

def test_family_on_one_number_newest_visit_first(db, conversation):
    out = ai_tools.find_patients(ctx_for(db, conversation))
    assert out["patients"] == [{"patient_id": "G502", "name": "DEMO KID"},
                               {"patient_id": "G501", "name": "DEMO MUM"}]       # (P) 拿掉，诊所自己不算
    assert "Ask which of these patients" in out["message"]


def test_new_patients_this_system_made_are_listed_once(db, conversation):
    kid2 = create_customer(db, "Demo Kid Two", PHONE)
    create_customer(db, "Linked Already", PHONE, gpis_contact_id=502)       # 已经录入 GPiS 的：只算 G502
    db.commit()
    out = ai_tools.find_patients(ctx_for(db, conversation))
    assert out["patients"][-1] == {"patient_id": f"N{kid2.id}", "name": "Demo Kid Two", "new_patient": True}
    assert len(out["patients"]) == 3


def test_number_nobody_uses_is_a_new_patient(db):
    out = ai_tools.find_patients(ctx_for(db, phone="60199999999"))
    assert out["patients"] == [] and "new patient" in out["message"] and "not the IC" in out["message"]


def test_names_from_gpis_dev_are_hidden(db, conversation):
    create_customer(db, "Demo New", PHONE)
    db.commit()
    dev = FakePatients(FAMILY.by_phone, fake_data=False)        # GPiS_Dev：真的病人
    out = ai_tools.find_patients(ctx_for(db, conversation, patients=dev))
    assert [p["name"] for p in out["patients"]] == [HIDDEN_NAME, HIDDEN_NAME, "Demo New"]
    assert "DEMO" not in str(out).replace("Demo New", "")


def test_patients_need_the_conversation(db):
    assert "needs the WhatsApp conversation" in ai_tools.find_patients(ctx_for(db))["error"]


def test_gpis_failure_when_finding_patients(db, conversation):
    class Down(FakePatients):
        def patients_for_phone(self, phone):
            raise RuntimeError("PWD=secret")

    out = ai_tools.find_patients(ctx_for(db, conversation, patients=Down()))
    assert "cannot be read right now" in out["error"] and "secret" not in out["error"]


# ---------- get_treatment_doctor ----------

def test_ortho_follow_up_goes_to_the_last_ortho_doctor(db, conversation):
    out = ai_tools.get_treatment_doctor(ctx_for(db, conversation), "g502", "OR")
    assert out == {"service": "OR", "doctor": "GOH", "name": "GOH"}


def test_not_multi_step_any_doctor(db, conversation):
    out = ai_tools.get_treatment_doctor(ctx_for(db, conversation), "G502", "S+P")
    assert out["doctor"] is None and "any doctor" in out["message"]


@pytest.mark.parametrize("patient_id", ["G501", "N1"])
def test_no_earlier_visit_hands_over(db, conversation, patient_id):
    if patient_id == "N1":
        patient_id = f"N{create_customer(db, 'Demo New', PHONE).id}"
        db.commit()
    out = ai_tools.get_treatment_doctor(ctx_for(db, conversation), patient_id, "OR")
    assert "No earlier ORTHO visit" in out["error"] and "hand over to staff" in out["error"]


def test_doctor_who_left_hands_over(db, conversation):
    db.get(Doctor, "GOH").active = False
    out = ai_tools.get_treatment_doctor(ctx_for(db, conversation), "G502", "OR")
    assert "No earlier ORTHO visit" in out["error"]


@pytest.mark.parametrize(("patient_id", "error"), [
    ("G777", "is not a patient of this WhatsApp number"),      # 别的号码的病人
    ("502", "is not valid"),
    ("DEMO KID", "is not valid"),
])
def test_patient_id_must_belong_to_this_number(db, conversation, patient_id, error):
    assert error in ai_tools.get_treatment_doctor(ctx_for(db, conversation), patient_id, "OR")["error"]


# ---------- create_appointment_request ----------

def test_book_a_gpis_patient(db, conversation):
    out = ai_tools.create_appointment_request(ctx_for(db, conversation), "s+p", "Dr Phang", "2026-10-23", "10:00",
                                              patient_id="G502")
    [r] = requests(db)
    assert out == {"request_id": r.id, "status": "PENDING", "patient_id": "G502", "service": "S+P", "doctor": "PHANG",
                   "date": "2026-10-23", "weekday": "Friday", "time": "10:00", "message": out["message"]}
    assert "clinic will confirm" in out["message"]
    assert (r.status, r.preferred_date, r.preferred_slot, r.duration_minutes) == (RequestStatus.PENDING, FRI, time(10), 30)
    assert r.conversation_id == conversation.id
    assert (r.customer.name, r.customer.phone, r.customer.gpis_contact_id) == ("DEMO KID", PHONE, 502)
    # 同一位病人再约：用同一个 Customer
    ai_tools.create_appointment_request(ctx_for(db, conversation), "C/UP", "PHANG", "2026-10-24", "9.30",
                                        patient_id="G502")
    assert db.scalar(select(func.count()).select_from(Customer)) == 1


def test_book_a_new_patient_then_book_again_with_their_id(db, conversation):
    out = ai_tools.create_appointment_request(ctx_for(db, conversation), "S+P", "PHANG", "2026-10-23", "10:00",
                                              new_patient_name="  Demo   New  ")
    new_id = out["patient_id"]
    assert new_id.startswith("N") and requests(db)[0].customer.name == "Demo New"
    assert ai_tools.find_patients(ctx_for(db, conversation))["patients"][-1]["patient_id"] == new_id
    out = ai_tools.create_appointment_request(ctx_for(db, conversation), "S+P", "PHANG", "2026-10-24", "10:00",
                                              patient_id=new_id)
    assert out["patient_id"] == new_id and len(requests(db)) == 2


def test_slot_is_checked_again_and_pending_requests_count(db, conversation):
    # 10:00 GPiS 已经 1 人；S+P 每格最多 3 人 → 再约 2 个就满了
    gpis = FakeGpis({(FRI, "PHANG"): [appt(1, "10:00")]})
    for name in ("Demo One", "Demo Two"):
        out = ai_tools.create_appointment_request(ctx_for(db, conversation, gpis=gpis), "S+P", "PHANG",
                                                  "2026-10-23", "10:00", new_patient_name=name)
        assert "request_id" in out
    out = ai_tools.create_appointment_request(ctx_for(db, conversation, gpis=gpis), "S+P", "PHANG",
                                              "2026-10-23", "10:00", new_patient_name="Demo Three")
    assert "10:00 with PHANG on 2026-10-23 is not free" in out["error"] and "10:30" in out["error"]
    assert len(requests(db)) == 2
    assert db.scalar(select(func.count()).select_from(Customer).where(Customer.name == "Demo Three")) == 0


def test_same_patient_same_day_twice(db, conversation):
    ai_tools.create_appointment_request(ctx_for(db, conversation), "S+P", "PHANG", "2026-10-23", "10:00",
                                        patient_id="G502")
    out = ai_tools.create_appointment_request(ctx_for(db, conversation), "C/UP", "PHANG", "2026-10-23", "14:00",
                                              patient_id="G502")
    assert "already has a request on 2026-10-23 (10:00" in out["error"]


def test_ortho_follow_up_only_with_the_original_doctor(db, conversation):
    out = ai_tools.create_appointment_request(ctx_for(db, conversation), "OR", "PHANG", "2026-10-23", "10:00",
                                              patient_id="G502")
    assert "must be with the doctor who started the treatment: GOH" in out["error"]
    out = ai_tools.create_appointment_request(ctx_for(db, conversation), "OR", "GOH", "2026-10-23", "10:00",
                                              patient_id="G502")
    assert out["doctor"] == "GOH"
    out = ai_tools.create_appointment_request(ctx_for(db, conversation), "OR", "GOH", "2026-10-24", "10:00",
                                              new_patient_name="Demo New")
    assert "no earlier ORTHO visit" in out["error"]


@pytest.mark.parametrize(("kwargs", "error"), [
    ({"patient_id": "G502", "new_patient_name": "Demo"}, "either patient_id"),
    ({}, "either patient_id"),
    ({"new_patient_name": "Ali 900101-01-1234"}, "name only"),
    ({"new_patient_name": "A"}, "2 to 60 characters"),
    ({"patient_id": "G777"}, "is not a patient of this WhatsApp number"),
])
def test_who_the_booking_is_for(db, conversation, kwargs, error):
    out = ai_tools.create_appointment_request(ctx_for(db, conversation), "S+P", "PHANG", "2026-10-23", "10:00", **kwargs)
    assert error in out["error"]
    assert requests(db) == []


@pytest.mark.parametrize(("args", "error"), [
    (("S+P", "PHANG", "2026-10-23", "10am"), "Use HH:MM"),
    (("S+P", "", "2026-10-23", "10:00"), "Choose a doctor"),
    (("S+P", "PHANG", "2026-10-21", "10:00"), "not after today"),
    (("RCT", "PHANG", "2026-10-23", "10:00"), "booked by staff"),
    (("S+P", "PHANG", "2026-10-23", "12:00"), "is not free"),             # 午休
    (("S+P", "GOH", "2026-10-22", "10:00"), "is not free"),               # GOH 星期四休息
])
def test_booking_details_are_checked(db, conversation, args, error):
    out = ai_tools.create_appointment_request(ctx_for(db, conversation), *args, patient_id="G502")
    assert error in out["error"]
    assert requests(db) == []


def test_booking_needs_the_conversation(db):
    out = ai_tools.create_appointment_request(ctx_for(db, phone=PHONE), "S+P", "PHANG", "2026-10-23", "10:00",
                                              patient_id="G502")
    assert "needs the WhatsApp conversation" in out["error"]


def test_failed_booking_keeps_data_made_before(db, conversation):
    """出错时 rollback：只取消这个工具做的事，之前已经存好的不受影响。"""
    create_customer(db, "Demo Saved", OTHER_PHONE)
    db.commit()
    ai_tools.create_appointment_request(ctx_for(db, conversation), "S+P", "PHANG", "2026-10-23", "25:00",
                                        patient_id="G502")
    assert db.scalar(select(func.count()).select_from(Customer).where(Customer.name == "Demo Saved")) == 1


def test_command_line_patients_with_demo_data(db, monkeypatch, capsys):
    from contextlib import nullcontext

    monkeypatch.setattr("app.db.session.new_session", lambda: nullcontext(db))
    monkeypatch.setattr("app.main._default_reader", lambda: FakeGpis())
    monkeypatch.setattr("app.config.reminder_source_name", lambda: "demo")
    monkeypatch.setattr("app.reminder_demo.DemoReminderSource.from_settings", classmethod(lambda cls: cls(PHONE)))
    assert ai_tools.main(["patients", "012-000 0001"]) == 0
    printed = capsys.readouterr().out
    assert "DEMO PATIENT A" in printed and "DEMO PATIENT B" in printed
    assert ai_tools.main(["book", "0120000001", "S+P", "PHANG", "2026-12-01", "10:00", "--new-name", "Demo"]) == 1
    assert "No open conversation" in capsys.readouterr().out
