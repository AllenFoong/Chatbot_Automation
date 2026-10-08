"""预约提醒的名单（Phase 5b 第一步：只看名单，D40、D54）。

- 每次都重新读 GPiS（员工会改、会删预约，W26），不存任何东西。
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
from ..db.models import Doctor
from ..db.rules import RulesNotConfigured, load_clinic_rules
from ..db.session import get_session
from ..gpis import GpisReader, WrongDatabaseError
from ..reminder_demo import DemoReminderSource
from ..reminders import (
    PhoneKind, ReminderGroup, ReminderSource, ReminderText, build_reminder_list, clinic_today, reminder_dates,
)

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


class ReminderGroupOut(BaseModel):
    key: str
    date: date
    phone: str | None
    phone_kind: PhoneKind
    lines: list[ReminderLineOut]
    problems: list[str]
    message: str | None
    whatsapp_allowed: bool


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


def _group_out(g: ReminderGroup, doctor_names: dict[str, str], allowed: bool) -> ReminderGroupOut:
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
    )


@router.get("", response_model=ReminderListOut)
def preview(
    date_: date | None = Query(None, alias="date", description="预约日期；不填 = 今天要提醒的日期（明天，假期前连后天）"),
    session: Session = Depends(get_session),
    source: ReminderSource = Depends(get_reminder_source),
    wa: WhatsAppSettings = Depends(get_whatsapp_settings),
    text: ReminderText = Depends(get_reminder_text),
) -> ReminderListOut:
    try:
        rules = load_clinic_rules(session)
        doctor_names = {d.id: d.display_name for d in session.scalars(select(Doctor))}
    except RulesNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except SQLAlchemyError as e:
        log.exception("读取本系统设置失败")
        raise HTTPException(status_code=503, detail="Cannot read the clinic settings. See the server log.") from e

    suggested = reminder_dates(clinic_today(), rules.closures)
    dates = [date_] if date_ else suggested
    read_at = datetime.now(timezone.utc)
    try:
        rows = source.reminder_appointments(min(dates), max(dates))
    except WrongDatabaseError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:  # 不把连接字符串或 driver 的详细错误回给调用方
        log.exception("读取 GPiS 失败")
        raise HTTPException(status_code=503, detail="Cannot read GPiS. See the server log.") from e

    result = build_reminder_list(dates, rows, rules, doctor_names, text)
    log.info("提醒名单：%d 天，可以发 %d 个号码，要员工看 %d 个", len(dates), len(result.ready), len(result.needs_staff))
    return ReminderListOut(
        dates=list(result.dates),
        suggested_dates=suggested,
        source=source.label,
        production=source.is_production,
        read_at=read_at,
        ready=[_group_out(g, doctor_names, whatsapp_allowed(g, source, wa)) for g in result.ready],
        needs_staff=[_group_out(g, doctor_names, False) for g in result.needs_staff],
        not_appointments=[CountOut(reason=r, count=n) for r, n in result.not_appointments],
    )
