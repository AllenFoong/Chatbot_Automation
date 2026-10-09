"""预约提醒在本系统数据库里记的东西（Phase 5b）：员工按过 Open in WhatsApp、没有发出去、号码不要提醒。

名单本身不存（每次都从 GPiS 重新算，app/reminders.py）；这里只有员工做过的事。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timezone

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from .conversations import get_or_create_wa_contact
from .models import OptOutBy, Reminder, ReminderStatus, Staff, WaContact


def _now() -> datetime:
    return datetime.now(timezone.utc)


def opted_out_phones(session: Session) -> frozenset[str]:
    """不要提醒的号码（D46、D55）。"""
    return frozenset(session.scalars(select(WaContact.wa_phone).where(WaContact.reminders_opt_out_at.is_not(None))))


def find_reminders(session: Session, keys: Iterable[tuple[date, str]]) -> dict[tuple[date, str], Reminder]:
    keys = list(keys)
    if not keys:
        return {}
    rows = session.scalars(
        select(Reminder)
        .where(tuple_(Reminder.appointment_date, Reminder.wa_phone).in_(keys))
        .options(selectinload(Reminder.staff))
    )
    return {(r.appointment_date, r.wa_phone): r for r in rows}


def record_opened(session: Session, day: date, phone: str, body: str, appointment_ids: Iterable[int],
                  staff: Staff) -> Reminder:
    """员工按了 Open in WhatsApp。同一个号码、同一天再按一次 = 更新同一条（UNIQUE，两位员工同时按也一样）。"""
    values = dict(status=ReminderStatus.OPENED, body=body, gpis_appointment_ids=sorted(set(appointment_ids)),
                  staff_id=staff.id, updated_at=func.now())
    session.execute(
        insert(Reminder)
        .values(appointment_date=day, wa_phone=phone, **values)
        .on_conflict_do_update(index_elements=["appointment_date", "wa_phone"], set_=values)
    )
    session.expire_all()
    return find_reminders(session, [(day, phone)])[(day, phone)]


def mark_not_sent(session: Session, day: date, phone: str, staff: Staff) -> Reminder | None:
    reminder = find_reminders(session, [(day, phone)]).get((day, phone))
    if reminder is not None:
        reminder.status = ReminderStatus.NOT_SENT
        reminder.staff_id = staff.id
        reminder.updated_at = _now()
        session.flush()
        session.refresh(reminder)
    return reminder


def set_opt_out(session: Session, phone: str, opted_out: bool, staff: Staff) -> WaContact:
    """员工标记这个号码不要提醒（签名表写 NO WA），或改回照常提醒。整个号码，家人也一起（D46）。"""
    contact = get_or_create_wa_contact(session, phone)
    if opted_out and contact.reminders_opt_out_at is None:
        contact.reminders_opt_out_at = _now()
        contact.reminders_opt_out_by = OptOutBy.STAFF
        contact.reminders_opt_out_staff_id = staff.id
    elif not opted_out:
        contact.reminders_opt_out_at = None
        contact.reminders_opt_out_by = None
        contact.reminders_opt_out_staff_id = None
    session.flush()
    return contact
