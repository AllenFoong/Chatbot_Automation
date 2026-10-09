"""预约提醒的名单（Phase 5b，D40、D54）。

- 每次都重新读 GPiS（员工会改、会删预约，W26），名单不存。
- 只记员工做过的事（reminders 表）：按过 Open in WhatsApp、没有发出去；号码不要提醒（opt-out，D55）。
- 回应里有病人名字和号码：员工本来就看得到（和 GPiS 一样），只在 Admin Platform 上显示，不写日志。
- Open in WhatsApp（D54）：只有读主机的 GPiS 时才给；读 GPiS_Dev 或假资料时，只给允许名单里的号码。
  这里还没有「系统自己发」：要等 5c（docs/architecture.md 第 10 节）。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..auth import current_staff
from ..config import (
    WhatsAppSettings, get_reminder_text, get_settings, get_whatsapp_settings, reminder_source_name,
)
from ..db.models import Doctor, Reminder, ReminderStatus, Staff
from ..db.reminders import find_reminders, mark_not_sent, opted_out_phones, record_opened, set_opt_out
from ..db.rules import RulesNotConfigured, load_clinic_rules
from ..db.session import get_session
from ..gpis import GpisReader, WrongDatabaseError
from ..reminder_demo import DemoReminderSource
from ..reminders import (
    PhoneKind, ReminderGroup, ReminderList, ReminderSource, ReminderText, build_reminder_list, clinic_today,
    reminder_dates,
)
from ..phone import normalize_phone

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reminders", tags=["reminders"], dependencies=[Depends(current_staff)])


class ReminderLineOut(BaseModel):
    appointment_ids: list[int]
    time: str | None
    doctor_id: str
    doctor_name: str
    patient_name: str
    status: str | None
    problems: list[str]


class ReminderRecordOut(BaseModel):
    """员工对这条提醒做过什么（reminders 表）。"""
    status: ReminderStatus
    updated_at: datetime
    staff_name: str | None
    changed: bool          # 之后 GPiS 多了 / 少了预约：要再看一次


class ReminderGroupOut(BaseModel):
    key: str
    date: date
    phone: str | None
    phone_kind: PhoneKind
    lines: list[ReminderLineOut]
    problems: list[str]
    message: str | None
    whatsapp_allowed: bool
    opted_out: bool
    record: ReminderRecordOut | None


class CountOut(BaseModel):
    reason: str
    count: int


class ReminderListOut(BaseModel):
    dates: list[date]
    suggested_dates: list[date]
    source: str
    production: bool
    read_at: datetime
    ready: list[ReminderGroupOut]
    needs_staff: list[ReminderGroupOut]
    not_appointments: list[CountOut]


@lru_cache
def _gpis_reader() -> GpisReader:
    s = get_settings()
    return GpisReader(s.gpis_connection_string, s.gpis_expected_database)


def get_reminder_source() -> ReminderSource:
    if reminder_source_name() == "demo":
        return DemoReminderSource.from_settings()
    try:
        return _gpis_reader()
    except RuntimeError as e:      # 没有设置 GPIS_CONNECTION_STRING
        raise HTTPException(status_code=503, detail=str(e)) from e


def whatsapp_allowed(group: ReminderGroup, source: ReminderSource, wa: WhatsAppSettings) -> bool:
    """Open in WhatsApp 的锁（D54）。允许名单写 * 也不算：不是正式资料时只认写出来的号码。"""
    if not group.ready or group.phone is None:
        return False
    if source.is_production:
        return True
    return wa.allowed_recipients is not None and group.phone in wa.allowed_recipients


def _appointment_ids(g: ReminderGroup) -> set[int]:
    return {i for ln in g.lines for i in ln.appointment_ids}


def _record_out(r: Reminder | None, g: ReminderGroup) -> ReminderRecordOut | None:
    if r is None:
        return None
    return ReminderRecordOut(
        status=r.status, updated_at=r.updated_at, staff_name=r.staff.name if r.staff else None,
        changed=set(r.gpis_appointment_ids) != _appointment_ids(g),
    )


def _group_out(g: ReminderGroup, doctor_names: dict[str, str], allowed: bool, opted_out: frozenset[str],
               records: dict[tuple[date, str], Reminder]) -> ReminderGroupOut:
    return ReminderGroupOut(
        key=f"{g.day.isoformat()}:{g.lines[0].appointment_ids[0]}",
        date=g.day,
        phone=g.phone,
        phone_kind=g.phone_kind,
        lines=[
            ReminderLineOut(
                appointment_ids=list(ln.appointment_ids),
                time=ln.slot.strftime("%H:%M") if ln.slot else None,
                doctor_id=ln.doctor_id,
                doctor_name=doctor_names.get(ln.doctor_id, ln.doctor_id),
                patient_name=ln.patient_name,
                status=ln.status,
                problems=list(ln.problems),
            )
            for ln in g.lines
        ],
        problems=list(g.problems),
        message=g.message,
        whatsapp_allowed=allowed,
        opted_out=g.phone in opted_out,
        record=_record_out(records.get((g.day, g.phone)) if g.phone else None, g),
    )


def _build(session: Session, source: ReminderSource, text: ReminderText, date_: date | None):
    """读设置和 GPiS，排好名单。回传 (名单, 建议的日期, 医生名字, 不要提醒的号码)。"""
    try:
        rules = load_clinic_rules(session)
        doctor_names = {d.id: d.display_name for d in session.scalars(select(Doctor))}
        opted_out = opted_out_phones(session)
    except RulesNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except SQLAlchemyError as e:
        log.exception("读取本系统设置失败")
        raise HTTPException(status_code=503, detail="Cannot read the clinic settings. See the server log.") from e

    suggested = reminder_dates(clinic_today(), rules.closures)
    dates = [date_] if date_ else suggested
    try:
        rows = source.reminder_appointments(min(dates), max(dates))
    except WrongDatabaseError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:  # 不把连接字符串或 driver 的详细错误回给调用方
        log.exception("读取 GPiS 失败")
        raise HTTPException(status_code=503, detail="Cannot read GPiS. See the server log.") from e
    result = build_reminder_list(dates, rows, rules, doctor_names, text, opted_out)
    return result, suggested, doctor_names, opted_out


@router.get("", response_model=ReminderListOut)
def preview(
    date_: date | None = Query(None, alias="date", description="预约日期；不填 = 今天要提醒的日期（明天，假期前连后天）"),
    session: Session = Depends(get_session),
    source: ReminderSource = Depends(get_reminder_source),
    wa: WhatsAppSettings = Depends(get_whatsapp_settings),
    text: ReminderText = Depends(get_reminder_text),
) -> ReminderListOut:
    read_at = datetime.now(timezone.utc)
    result, suggested, doctor_names, opted_out = _build(session, source, text, date_)
    log.info("提醒名单：%d 天，可以发 %d 个号码，要员工看 %d 个", len(result.dates), len(result.ready), len(result.needs_staff))
    groups = result.ready + result.needs_staff
    records = find_reminders(session, {(g.day, g.phone) for g in groups if g.phone})
    return ReminderListOut(
        dates=list(result.dates),
        suggested_dates=suggested,
        source=source.label,
        production=source.is_production,
        read_at=read_at,
        ready=[_group_out(g, doctor_names, whatsapp_allowed(g, source, wa), opted_out, records) for g in result.ready],
        needs_staff=[_group_out(g, doctor_names, False, opted_out, records) for g in result.needs_staff],
        not_appointments=[CountOut(reason=r, count=n) for r, n in result.not_appointments],
    )


# ---------- 员工做过的事 ----------

class ReminderKeyIn(BaseModel):
    date: date
    phone: str


class OptOutIn(BaseModel):
    phone: str
    opted_out: bool


class OptOutOut(BaseModel):
    phone: str
    opted_out: bool


def _phone(raw: str) -> str:
    phone = normalize_phone(raw)
    if phone is None:
        raise HTTPException(status_code=422, detail="Not a phone number.")
    return phone


def _find_ready(result: ReminderList, day: date, phone: str) -> ReminderGroup | None:
    return next((g for g in result.ready if g.day == day and g.phone == phone), None)


@router.post("/opened", response_model=ReminderRecordOut)
def opened(
    body: ReminderKeyIn,
    session: Session = Depends(get_session),
    staff: Staff = Depends(current_staff),
    source: ReminderSource = Depends(get_reminder_source),
    wa: WhatsAppSettings = Depends(get_whatsapp_settings),
    text: ReminderText = Depends(get_reminder_text),
) -> ReminderRecordOut:
    """员工按了 Open in WhatsApp：记下来（谁、几点、消息、哪几个预约）。

    重新读一次 GPiS、重新算那一天：不信任画面送来的消息，也确认这个号码还在 Ready、还可以打开（D54 的锁）。
    """
    phone = _phone(body.phone)
    result, _, _, _ = _build(session, source, text, body.date)
    group = _find_ready(result, body.date, phone)
    if group is None or group.message is None:
        raise HTTPException(status_code=409, detail="This reminder is not ready any more. Refresh the list.")
    if not whatsapp_allowed(group, source, wa):
        raise HTTPException(status_code=403, detail="Open in WhatsApp is off for this number.")
    reminder = record_opened(session, body.date, phone, group.message, _appointment_ids(group), staff)
    session.commit()
    log.info("提醒：员工 %d 按了 Open in WhatsApp（%s）", staff.id, body.date.isoformat())
    return _record_out(reminder, group)


@router.post("/not-sent", response_model=ReminderRecordOut)
def not_sent(
    body: ReminderKeyIn,
    session: Session = Depends(get_session),
    staff: Staff = Depends(current_staff),
) -> ReminderRecordOut:
    """员工说没有发出去（按错了、病人刚打电话来）：改回没发，名单上可以再按。"""
    reminder = mark_not_sent(session, body.date, _phone(body.phone), staff)
    if reminder is None:
        raise HTTPException(status_code=404, detail="This reminder was never opened.")
    session.commit()
    return ReminderRecordOut(status=reminder.status, updated_at=reminder.updated_at,
                             staff_name=staff.name, changed=False)


@router.put("/opt-out", response_model=OptOutOut)
def opt_out(
    body: OptOutIn,
    session: Session = Depends(get_session),
    staff: Staff = Depends(current_staff),
) -> OptOutOut:
    """这个号码不要提醒（签名表的 Remark 写 NO WA，D55），或改回照常提醒。整个号码，家人也一起。"""
    contact = set_opt_out(session, _phone(body.phone), body.opted_out, staff)
    session.commit()
    log.info("提醒：员工 %d 把一个号码改成%s", staff.id, "不要提醒" if body.opted_out else "照常提醒")
    return OptOutOut(phone=contact.wa_phone, opted_out=contact.reminders_opt_out_at is not None)
