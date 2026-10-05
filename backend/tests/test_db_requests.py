"""病人和预约请求（全部是假名字、假号码）。"""

from datetime import date, time

import pytest

from app.db import conversations as conv
from app.db.appointment_requests import (
    InvalidTransition,
    cancel_request,
    confirm_request,
    create_appointment_request,
    list_pending_requests,
    new_group_id,
    reject_request,
)
from app.db.customers import create_customer, customers_booked_via, find_customers_by_phone
from app.db.models import AppointmentRequest, RequestStatus, Service
from app.db.seed import seed
from tests.database import add_staff, assert_rejected

FRI = date(2026, 10, 9)


@pytest.fixture
def db(session):
    seed(session)       # 预约请求要用到疗程代码和医生
    return session


def test_family_members_share_one_number(db):
    mum = create_customer(db, "Test Mum", "012-345 6789")
    kid = create_customer(db, "Test Kid", "0123456789")
    create_customer(db, "Someone Else", "+65 9123 4567")
    assert find_customers_by_phone(db, "+60123456789") == [mum, kid]
    assert find_customers_by_phone(db, "12345") == []


def test_customer_input_is_checked(db):
    with pytest.raises(ValueError):
        create_customer(db, "   ")
    with pytest.raises(ValueError):
        create_customer(db, "Test Patient", "12345")
    assert create_customer(db, " Test Patient ").name == "Test Patient"


def test_customers_booked_via_a_whatsapp_number(db):
    msg, _ = conv.record_incoming_message(db, "60123456789", "Book for my mother please", "wamid.1")
    grandma = create_customer(db, "Test Grandma", "0198765432")     # 她自己的号码不一样
    create_appointment_request(db, grandma, "C/UP", conversation=msg.conversation)
    assert customers_booked_via(db, msg.conversation.wa_contact_id) == [grandma]
    assert find_customers_by_phone(db, "60123456789") == []


def test_new_request_is_pending(db):
    patient = create_customer(db, "Test Patient", "0123456789")
    r = create_appointment_request(db, patient, " s+p ", doctor_id="phang", preferred_date=FRI,
                                   preferred_slot=time(10, 30))
    assert (r.status, r.service_code, r.doctor_id, r.duration_minutes) == (RequestStatus.PENDING, "S+P", "PHANG", 30)
    assert r.handled_at is None and r.created_at is not None
    assert list_pending_requests(db) == [r]


def test_unknown_or_inactive_service_and_doctor(db):
    patient = create_customer(db, "Test Patient")
    db.get(Service, "XLA").active = False
    for kwargs in (dict(service_code="NOPE"), dict(service_code="XLA"), dict(service_code="S+P", doctor_id="CHER")):
        with pytest.raises(ValueError):
            create_appointment_request(db, patient, **kwargs)


@pytest.mark.parametrize("values", [
    dict(preferred_slot=time(10, 30)),                          # 有时段没有日期
    dict(preferred_date=FRI, preferred_slot=time(10, 15)),      # 不在 30 分钟的格上
    dict(duration_minutes=45),
    dict(duration_minutes=0),
    dict(status=RequestStatus.CONFIRMED),                       # 确认了却没有 handled_at
])
def test_database_rejects_bad_requests(db, values):
    patient = create_customer(db, "Test Patient")
    row = {"customer_id": patient.id, "service_code": "S+P", "status": RequestStatus.PENDING, **values}
    assert_rejected(db, AppointmentRequest(**row))


def test_confirm_then_patient_cancels(db):
    amy = add_staff(db)
    r = create_appointment_request(db, create_customer(db, "Test Patient"), "S+P")
    confirm_request(db, r, amy, gpis_appointment_id=123456)
    assert (r.status, r.handled_by, r.gpis_appointment_id) == (RequestStatus.CONFIRMED, amy.id, 123456)
    assert r.handled_at is not None
    assert list_pending_requests(db) == []

    cancel_request(db, r)           # 病人在 WhatsApp 上取消
    assert r.status == RequestStatus.CANCELLED and r.handled_by is None
    with pytest.raises(InvalidTransition):
        confirm_request(db, r, amy)


def test_rejected_request_is_final(db):
    amy = add_staff(db)
    r = create_appointment_request(db, create_customer(db, "Test Patient"), "C/UP")
    reject_request(db, r, amy)
    with pytest.raises(InvalidTransition):
        confirm_request(db, r, amy)
    with pytest.raises(InvalidTransition):
        cancel_request(db, r)


def test_family_coming_together_share_group_id(db):
    group = new_group_id()
    mum = create_customer(db, "Test Mum", "0123456789")
    kid = create_customer(db, "Test Kid", "0123456789")
    a = create_appointment_request(db, mum, "S+P", preferred_date=FRI, preferred_slot=time(16), group_id=group)
    b = create_appointment_request(db, kid, "S+P", preferred_date=FRI, preferred_slot=time(16), group_id=group)
    db.expire_all()
    assert a.group_id == b.group_id == group
