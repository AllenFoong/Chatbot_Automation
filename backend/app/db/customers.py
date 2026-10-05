"""病人。一个 WhatsApp 号码可能对应几位病人（家人共用，统计 B11），AI 要先问清楚是哪一位。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..phone import normalize_phone
from .models import AppointmentRequest, Conversation, Customer


def create_customer(
    session: Session, name: str, phone: str | None = None, gpis_contact_id: int | None = None
) -> Customer:
    name = name.strip()
    if not name:
        raise ValueError("病人名字不能空白")
    normalized = None
    if phone:
        normalized = normalize_phone(phone)
        if normalized is None:
            raise ValueError("看不懂的电话号码")   # 不把号码写进错误信息（会进日志）
    customer = Customer(name=name, phone=normalized, gpis_contact_id=gpis_contact_id)
    session.add(customer)
    session.flush()
    return customer


def find_customers_by_phone(session: Session, phone: str) -> list[Customer]:
    """用电话找病人（先转成国际格式再比对）。可能找到几位。"""
    normalized = normalize_phone(phone)
    if normalized is None:
        return []
    return list(session.scalars(select(Customer).where(Customer.phone == normalized).order_by(Customer.id)))


def customers_booked_via(session: Session, wa_contact_id: int) -> list[Customer]:
    """这个 WhatsApp 号码以前帮哪几位病人预约过（不一定是他们自己的号码，例：儿子帮妈妈约）。"""
    return list(
        session.scalars(
            select(Customer)
            .join(AppointmentRequest, AppointmentRequest.customer_id == Customer.id)
            .join(Conversation, AppointmentRequest.conversation_id == Conversation.id)
            .where(Conversation.wa_contact_id == wa_contact_id)
            .distinct()
            .order_by(Customer.id)
        )
    )
