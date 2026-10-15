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

from ..auth import current_staff
from ..config import WhatsAppSettings, get_reminder_text, get_whatsapp_settings
from ..confirm import GpisChoice, RequestFacts, gpis_choices, match_score, may_send, rank, render_confirmation
from ..db import appointment_requests as reqs
from ..db import conversations as conv
from ..db.models import (
    AppointmentRequest, ClinicSettings, Conversation, ConversationMode, Customer, Doctor, RequestStatus, Sender,
    Staff, WaStatus,
)
from ..db.session import get_session
from ..gpis import WrongDatabaseError
from ..reminders import ReminderSource
from ..whatsapp import RecipientNotAllowed, WhatsAppClient, WhatsAppError, WhatsAppNotConfigured, get_whatsapp_client
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


def _used_by(session: Session, appointment_ids: list[int], request_id: int) -> dict[int, int]:
    if not appointment_ids:
        return {}
    rows = session.execute(
        select(AppointmentRequest.gpis_appointment_id, AppointmentRequest.id).where(
            AppointmentRequest.status == RequestStatus.CONFIRMED,
            AppointmentRequest.gpis_appointment_id.in_(appointment_ids),
            AppointmentRequest.id != request_id,
        )
    )
    return {gpis_id: rid for gpis_id, rid in rows}


def _doctor_names(session: Session) -> dict[str, str]:
    return {d.id: d.display_name for d in session.scalars(select(Doctor))}


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
    used = _used_by(session, [c.appointment_id for c in choices], r.id)
    names = _doctor_names(session)
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


def _link_contact(session: Session, customer: Customer, contact_id: int | None) -> None:
    """新病人：记下 GPiS 的 ContactID，下次就认得（D71）。已经有、或别的病人用了这个 ID，就不改。"""
    if customer.gpis_contact_id is not None or contact_id is None:
        return
    taken = session.scalar(select(Customer.id).where(Customer.gpis_contact_id == contact_id))
    if taken is None:
        customer.gpis_contact_id = contact_id


def _notify(
    session: Session, r: AppointmentRequest, source: ReminderSource, whatsapp: WhatsAppClient, staff: Staff
) -> None:
    """确认之后马上经 WhatsApp 通知病人；发不了就留在「要通知」，写原因。"""
    message = r.confirm_message or ""
    if not may_send(source):
        reqs.notify_failed(session, r, f"Not sent: the GPiS list comes from {source.label} (test data with real "
                                       "patient names). Use demo data or the clinic's GPiS to send.")
        return
    if r.conversation is None:
        reqs.notify_failed(session, r, "No WhatsApp conversation (the request was added by staff)")
        return
    contact = r.conversation.wa_contact
    if not conv.customer_service_window_open(session, contact.id):
        reqs.notify_failed(session, r, "More than 24 hours since the patient's last message: WhatsApp only allows "
                                       "approved templates now")
        return
    open_conversation = conv.get_open_conversation(session, contact.id)
    if open_conversation is None:
        reqs.notify_failed(session, r, "The WhatsApp conversation is closed")
        return
    try:
        wa_message_id = whatsapp.send_text(contact.wa_phone, message)
    except RecipientNotAllowed:
        reqs.notify_failed(session, r, "This number is not in WHATSAPP_ALLOWED_RECIPIENTS (development)")
        return
    except WhatsAppNotConfigured:
        reqs.notify_failed(session, r, "WhatsApp is not set up on this computer")
        return
    except WhatsAppError as e:
        reqs.notify_failed(session, r, f"WhatsApp did not accept the message: {e}")
        return
    try:
        # AI 在回复的对话：算 AI（系统）发的，AI 照常继续；员工接手的对话：算这位员工发的（不会变成接手）
        if open_conversation.mode == ConversationMode.BOT:
            conv.record_outgoing_message(session, open_conversation, Sender.BOT, message,
                                         wa_message_id=wa_message_id, wa_status=WaStatus.ACCEPTED)
        else:
            conv.record_outgoing_message(session, open_conversation, Sender.STAFF, message, staff=staff,
                                         wa_message_id=wa_message_id, wa_status=WaStatus.ACCEPTED)
        reqs.patient_notified(session, r)
        session.commit()
    except Exception:
        # 病人已经收到了，但记录没存进去：留下消息 ID，方便查；请求留在「要通知」
        log.exception("确认消息已经发出，但存进数据库失败（%s）", wa_message_id)
        session.rollback()
        reqs.notify_failed(session, r, "The message was sent, but saving it failed. Check the WhatsApp chat "
                                       "before telling the patient again.")


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
    used = _used_by(session, [choice.appointment_id], r.id)
    if used:
        raise HTTPException(status_code=409, detail="This GPiS appointment already confirms another request")

    names = _doctor_names(session)
    message = render_confirmation(choice, names.get(choice.doctor_id, choice.doctor_id), get_reminder_text())
    _link_contact(session, r.customer, choice.contact_id)
    reqs.confirm_request(
        session, r, staff, choice.appointment_id,
        confirmed_date=choice.day, confirmed_slot=choice.slot, confirmed_doctor_id=choice.doctor_id,
        confirm_message=message,
    )
    session.commit()                                   # 先存 CONFIRMED，再发：中途当机的留在「要通知」

    assert source is not None                          # _read_gpis_day 已经检查过
    _notify(session, r, source, whatsapp, staff)
    session.commit()
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
