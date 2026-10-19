"""预约请求：员工看待确认的请求，在 GPiS 录入后确认；或拒绝、帮病人取消（D6）。

确认（D71 ①，Phase 6a-2b）：
- 员工按 Entered in GPiS ✓ → GET /{id}/gpis 当场只读查一次 GPiS，列出那一天的预约（和请求一样的排最上面）。
- 员工点选一个 → POST /{id}/confirm 再查一次 GPiS（那个预约还在才确认）→ CONFIRMED，记下 AppointmentID 和
  GPiS 上的日期、时间、医生；新病人顺便记下 ContactID。GPiS 里找不到 = 不能确认（先在 GPiS 输入）。
- 确认后马上经 WhatsApp 通知病人（照 GPiS 写的）。发不了（超过 24 小时、读 GPiS_Dev、没设定 WhatsApp …）
  → 留在「要通知」（to_tell=true），写原因；员工用 Open in WhatsApp 或手机传了，按 Patient told ✓。
  先存 CONFIRMED 再发：中途当机的，留在「要通知」，不自动重发（病人可能已经收到，D45）。
- 回应里有病人名字：员工本来就看得到（和 GPiS 一样），只在 Admin Platform 上显示，不写日志。
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import auto_confirm
from ..auth import current_staff
from ..config import WhatsAppSettings, get_whatsapp_settings
from ..confirm import GpisChoice, RequestFacts, gpis_choices, match_score, may_send, rank
from ..confirming import confirm_choice, doctor_names, used_by
from ..db import appointment_requests as reqs
from ..db.models import AppointmentRequest, ClinicSettings, Conversation, RequestStatus, Staff
from ..db.session import get_session
from ..gpis import WrongDatabaseError
from ..reminders import ReminderSource
from ..whatsapp import WhatsAppClient, get_whatsapp_client
from .reminders import get_reminder_source

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/requests", tags=["appointment requests"], dependencies=[Depends(current_staff)])


class RequestOut(BaseModel):
    id: int
    status: RequestStatus
    customer_id: int
    customer_name: str
    customer_phone: str | None
    gpis_contact_id: int | None
    conversation_id: int | None
    service_code: str
    service_name: str
    doctor_id: str | None
    preferred_date: date | None
    preferred_slot: time | None
    duration_minutes: int
    notes: str | None
    group_id: uuid.UUID | None
    gpis_appointment_id: int | None
    confirmed_date: date | None
    confirmed_slot: time | None
    confirmed_doctor_id: str | None
    confirm_message: str | None
    patient_told_at: datetime | None
    patient_told_by: int | None
    notify_problem: str | None
    whatsapp_phone: str | None       # 通知病人用的号码：对话的 WhatsApp 号码，没有对话就用病人的号码
    whatsapp_allowed: bool           # 能不能给 Open in WhatsApp（D54 的锁）
    handled_by: int | None
    handled_at: datetime | None
    created_at: datetime


class GpisChoiceOut(BaseModel):
    appointment_id: int
    date: dt.date
    time: str
    doctor_id: str
    doctor_name: str
    patient_name: str
    contact_id: int | None
    same_patient: bool
    same_doctor: bool
    same_time: bool
    used_by_request_id: int | None   # 已经确认了别的请求：不能再选


class GpisChoicesOut(BaseModel):
    date: dt.date
    source: str
    can_notify: bool                 # 确认后能不能经 WhatsApp 通知（读 GPiS_Dev 时不能）
    choices: list[GpisChoiceOut]


class ConfirmIn(BaseModel):
    gpis_appointment_id: int = Field(description="员工点选的 GPiS 预约（GET /{id}/gpis 列出来的）")
    date: dt.date | None = Field(None, description="那个预约的日期；不填 = 请求的日期")


def get_confirm_source() -> ReminderSource | None:
    """和提醒同一个来源（GPiS 或假资料，REMINDER_SOURCE）。没设定 GPiS 也照样能看请求，只是不能确认。"""
    try:
        return get_reminder_source()
    except HTTPException:
        return None


def _whatsapp_phone(r: AppointmentRequest) -> str | None:
    return r.conversation.wa_contact.wa_phone if r.conversation else r.customer.phone


def _open_allowed(phone: str | None, source: ReminderSource | None, wa: WhatsAppSettings) -> bool:
    """Open in WhatsApp（D54）：正式资料才给；假资料只给允许名单里写出来的号码；读 GPiS_Dev 不给。"""
    if phone is None or source is None or not may_send(source):
        return False
    if source.is_production:
        return True
    return wa.allowed_recipients is not None and phone in wa.allowed_recipients


def _out(r: AppointmentRequest, source: ReminderSource | None, wa: WhatsAppSettings) -> RequestOut:
    phone = _whatsapp_phone(r)
    return RequestOut(
        id=r.id, status=r.status,
        customer_id=r.customer_id, customer_name=r.customer.name, customer_phone=r.customer.phone,
        gpis_contact_id=r.customer.gpis_contact_id, conversation_id=r.conversation_id,
        service_code=r.service_code, service_name=r.service.name, doctor_id=r.doctor_id,
        preferred_date=r.preferred_date, preferred_slot=r.preferred_slot, duration_minutes=r.duration_minutes,
        notes=r.notes, group_id=r.group_id, gpis_appointment_id=r.gpis_appointment_id,
        confirmed_date=r.confirmed_date, confirmed_slot=r.confirmed_slot, confirmed_doctor_id=r.confirmed_doctor_id,
        confirm_message=r.confirm_message, patient_told_at=r.patient_told_at, patient_told_by=r.patient_told_by,
        notify_problem=r.notify_problem, whatsapp_phone=phone,
        whatsapp_allowed=r.status == RequestStatus.CONFIRMED and r.patient_told_at is None
        and r.confirm_message is not None and _open_allowed(phone, source, wa),
        handled_by=r.handled_by, handled_at=r.handled_at, created_at=r.created_at,
    )


_LOAD = (
    selectinload(AppointmentRequest.customer),
    selectinload(AppointmentRequest.service),
    selectinload(AppointmentRequest.conversation).selectinload(Conversation.wa_contact),
)


class AutoConfirmOut(BaseModel):
    enabled: bool                    # Settings 的开关（只有 ADMIN 能改）
    runs_here: bool                  # 这台电脑的资料来源可以自动确认（主机的 GPiS 或假资料；GPiS_Dev 不行）
    source: str | None
    checked_at: datetime | None      # 上次成功查 GPiS
    error: str | None
    in_business_hours: bool          # 9:00–17:30 才找
    stale: bool                      # 打开了、营业时间，超过 15 分钟没成功查 GPiS → 红字


@router.get("/auto-confirm", response_model=AutoConfirmOut)
def auto_confirm_status(
    session: Session = Depends(get_session),
    source: ReminderSource | None = Depends(get_confirm_source),
) -> AutoConfirmOut:
    """Requests 页面上面那一行：自动确认开了没有、上次成功查 GPiS 是几点（D71 ②）。"""
    settings = session.get(ClinicSettings, 1)
    if settings is None:
        raise HTTPException(status_code=503, detail="Clinic settings are missing: run python -m app.db.seed")
    return AutoConfirmOut(**auto_confirm.status(settings, source).__dict__)


@router.get("", response_model=list[RequestOut])
def list_requests(
    status: RequestStatus = Query(RequestStatus.PENDING),
    to_tell: bool = Query(False, description="true = 「要通知」：确认了、病人还不知道的（不看 status）"),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
    source: ReminderSource | None = Depends(get_confirm_source),
    wa: WhatsAppSettings = Depends(get_whatsapp_settings),
) -> list[RequestOut]:
    """PENDING、要通知：先来的排前面（先处理）；其他状态：最近的排前面。"""
    stmt = select(AppointmentRequest).options(*_LOAD).limit(limit)
    if to_tell:
        stmt = stmt.where(
            AppointmentRequest.status == RequestStatus.CONFIRMED, AppointmentRequest.patient_told_at.is_(None)
        ).order_by(AppointmentRequest.handled_at, AppointmentRequest.id)
    else:
        order = (AppointmentRequest.created_at, AppointmentRequest.id)
        if status != RequestStatus.PENDING:
            order = tuple(o.desc() for o in order)
        stmt = stmt.where(AppointmentRequest.status == status).order_by(*order)
    return [_out(r, source, wa) for r in session.scalars(stmt)]


def _get(session: Session, request_id: int, *, lock: bool = False) -> AppointmentRequest:
    r = session.get(AppointmentRequest, request_id, with_for_update=lock)
    if r is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return r


def _change(session: Session, request_id: int, change, source, wa) -> RequestOut:
    r = _get(session, request_id)
    try:
        change(r)
    except reqs.InvalidTransition as e:
        raise HTTPException(status_code=409, detail=f"A {r.status} request cannot be changed like this") from e
    session.commit()
    session.refresh(r)
    return _out(r, source, wa)


# ---------- 确认：当场查 GPiS ----------

def _read_gpis_day(source: ReminderSource | None, session: Session, day: date) -> list[GpisChoice]:
    if source is None:
        raise HTTPException(status_code=503, detail="GPiS is not set up on this computer (GPIS_CONNECTION_STRING)")
    settings = session.get(ClinicSettings, 1)
    if settings is None:
        raise HTTPException(status_code=503, detail="Clinic settings are missing: run python -m app.db.seed")
    try:
        rows = source.reminder_appointments(day, day)
    except WrongDatabaseError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:  # 不把连接字符串或 driver 的详细错误回给画面
        log.exception("确认请求时读取 GPiS 失败")
        raise HTTPException(status_code=503, detail="Could not read GPiS. Please try again, or see the server log.") \
            from e
    return gpis_choices([a for a in rows if a.appointment_date == day], settings.clinic_contact_id)


def _pending(session: Session, request_id: int, *, lock: bool = False) -> AppointmentRequest:
    r = _get(session, request_id, lock=lock)
    if r.status != RequestStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"This request is already {r.status.lower()}")
    return r


def _day(r: AppointmentRequest, chosen: date | None) -> date:
    day = chosen or r.preferred_date
    if day is None:
        raise HTTPException(status_code=422, detail="The request has no date: choose the date booked in GPiS")
    return day


def _facts(r: AppointmentRequest) -> RequestFacts:
    return RequestFacts(contact_id=r.customer.gpis_contact_id, doctor_id=r.doctor_id, slot=r.preferred_slot)


@router.get("/{request_id}/gpis", response_model=GpisChoicesOut)
def gpis_appointments(
    request_id: int,
    date_: date | None = Query(None, alias="date", description="不填 = 请求的日期"),
    session: Session = Depends(get_session),
    source: ReminderSource | None = Depends(get_confirm_source),
) -> GpisChoicesOut:
    """GPiS 那一天的预约，给员工点选（只有时间、名字、医生；没有 Remarks）。"""
    r = _pending(session, request_id)
    day = _day(r, date_)
    facts = _facts(r)
    choices = rank(_read_gpis_day(source, session, day), facts)
    used = used_by(session, [c.appointment_id for c in choices], r.id)
    names = doctor_names(session)
    return GpisChoicesOut(
        date=day,
        source=source.label,
        can_notify=may_send(source),
        choices=[
            GpisChoiceOut(
                appointment_id=c.appointment_id, date=c.day, time=c.slot.strftime("%H:%M"),
                doctor_id=c.doctor_id, doctor_name=names.get(c.doctor_id, c.doctor_id),
                patient_name=c.patient_name, contact_id=c.contact_id,
                same_patient=match_score(c, RequestFacts(facts.contact_id, None, None)) > 0,
                same_doctor=match_score(c, RequestFacts(None, facts.doctor_id, None)) > 0,
                same_time=match_score(c, RequestFacts(None, None, facts.slot)) > 0,
                used_by_request_id=used.get(c.appointment_id),
            )
            for c in choices
        ],
    )


@router.post("/{request_id}/confirm", response_model=RequestOut)
def confirm(
    request_id: int,
    body: ConfirmIn,
    staff: Staff = Depends(current_staff),
    session: Session = Depends(get_session),
    source: ReminderSource | None = Depends(get_confirm_source),
    wa: WhatsAppSettings = Depends(get_whatsapp_settings),
    whatsapp: WhatsAppClient = Depends(get_whatsapp_client),
) -> RequestOut:
    """员工已经在 GPiS 录入、点选了那个预约：再查一次 GPiS，还在才确认，然后通知病人。"""
    r = _pending(session, request_id, lock=True)       # 两位员工同时按：第二位等第一位做完，再看到不是 PENDING
    day = _day(r, body.date)
    choice = next(
        (c for c in _read_gpis_day(source, session, day) if c.appointment_id == body.gpis_appointment_id), None
    )
    if choice is None:
        raise HTTPException(
            status_code=409,
            detail=f"GPiS has no appointment {body.gpis_appointment_id} on {day:%d/%m/%Y} (or it was cancelled). "
                   "Enter it in GPiS first, then try again.",
        )
    if used_by(session, [choice.appointment_id], r.id):
        raise HTTPException(status_code=409, detail="This GPiS appointment already confirms another request")

    assert source is not None                          # _read_gpis_day 已经检查过
    confirm_choice(session, r, choice, staff, source, whatsapp)
    session.refresh(r)
    return _out(r, source, wa)


@router.post("/{request_id}/patient-told", response_model=RequestOut)
def patient_told(
    request_id: int,
    staff: Staff = Depends(current_staff),
    session: Session = Depends(get_session),
    source: ReminderSource | None = Depends(get_confirm_source),
    wa: WhatsAppSettings = Depends(get_whatsapp_settings),
) -> RequestOut:
    """员工自己通知了病人（Open in WhatsApp、手机）：从「要通知」拿掉。"""
    return _change(session, request_id, lambda r: reqs.patient_told(session, r, staff), source, wa)


@router.post("/{request_id}/reject", response_model=RequestOut)
def reject(
    request_id: int,
    staff: Staff = Depends(current_staff),
    session: Session = Depends(get_session),
    source: ReminderSource | None = Depends(get_confirm_source),
    wa: WhatsAppSettings = Depends(get_whatsapp_settings),
) -> RequestOut:
    return _change(session, request_id, lambda r: reqs.reject_request(session, r, staff), source, wa)


@router.post("/{request_id}/reopen", response_model=RequestOut)
def reopen(
    request_id: int,
    session: Session = Depends(get_session),
    source: ReminderSource | None = Depends(get_confirm_source),
    wa: WhatsAppSettings = Depends(get_whatsapp_settings),
) -> RequestOut:
    """拒绝、取消按错了：改回 Pending（Back to pending）。确认过又取消的，要重新点选 GPiS 的预约。"""
    return _change(session, request_id, lambda r: reqs.reopen_request(session, r), source, wa)


@router.post("/{request_id}/cancel", response_model=RequestOut)
def cancel(
    request_id: int,
    staff: Staff = Depends(current_staff),
    session: Session = Depends(get_session),
    source: ReminderSource | None = Depends(get_confirm_source),
    wa: WhatsAppSettings = Depends(get_whatsapp_settings),
) -> RequestOut:
    """病人取消。已经确认的，员工也要在 GPiS 把预约改成 Canceled。"""
    return _change(session, request_id, lambda r: reqs.cancel_request(session, r, staff), source, wa)
