"""预约请求：AI（或员工）建立 PENDING → 员工确认后手动录入 GPiS（D6）。

状态只能这样改：
  PENDING   → CONFIRMED / REJECTED / CANCELLED
  CONFIRMED → CANCELLED（确认之后病人又取消：员工也要在 GPiS 改成 Canceled）
  REJECTED / CANCELLED → PENDING（按错了：Back to pending，reopen_request）

这里只 flush，不 commit。
"""

from __future__ import annotations

import uuid
from datetime import date, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..availability import HeldRequest
from .models import AppointmentRequest, Conversation, Customer, Doctor, RequestStatus, Service, Staff

_ALLOWED = {
    RequestStatus.PENDING: {RequestStatus.CONFIRMED, RequestStatus.REJECTED, RequestStatus.CANCELLED},
    RequestStatus.CONFIRMED: {RequestStatus.CANCELLED},
}


class InvalidTransition(Exception):
    pass


def new_group_id() -> uuid.UUID:
    """几位病人一起来（Remarks 的 WITH，W8）：他们的请求用同一个 group_id。"""
    return uuid.uuid4()


def create_appointment_request(
    session: Session,
    customer: Customer,
    service_code: str,
    *,
    conversation: Conversation | None = None,
    doctor_id: str | None = None,
    preferred_date: date | None = None,
    preferred_slot: time | None = None,
    duration_minutes: int = 30,
    notes: str | None = None,
    group_id: uuid.UUID | None = None,
) -> AppointmentRequest:
    code = service_code.strip().upper()
    service = session.get(Service, code)
    if service is None or not service.active:
        raise ValueError(f"没有这个疗程代码：{code}")
    if doctor_id is not None:
        doctor_id = doctor_id.strip().upper()
        doctor = session.get(Doctor, doctor_id)
        if doctor is None or not doctor.active:
            raise ValueError(f"没有这位医生：{doctor_id}")

    request = AppointmentRequest(
        customer_id=customer.id,
        conversation_id=conversation.id if conversation else None,
        service_code=code,
        doctor_id=doctor_id,
        preferred_date=preferred_date,
        preferred_slot=preferred_slot,
        duration_minutes=duration_minutes,
        status=RequestStatus.PENDING,
        notes=notes,
        group_id=group_id,
    )
    session.add(request)
    session.flush()
    return request


def _change_status(request: AppointmentRequest, new: RequestStatus, staff: Staff | None) -> None:
    if new not in _ALLOWED.get(request.status, set()):
        raise InvalidTransition(f"{request.status} 不能改成 {new}")
    request.status = new
    request.handled_by = staff.id if staff else None
    request.handled_at = func.now()


def confirm_request(
    session: Session,
    request: AppointmentRequest,
    staff: Staff | None,
    gpis_appointment_id: int | None = None,
    *,
    confirmed_date: date | None = None,
    confirmed_slot: time | None = None,
    confirmed_doctor_id: str | None = None,
    confirm_message: str | None = None,
) -> None:
    """确认：员工在 GPiS 录入后点选了那个预约（D71 ①）；staff = None 是系统自动确认（D71 ②，6a-2c）。

    之后这个请求在「要通知」，直到系统发出确认消息（patient_notified）或员工按 Patient told ✓（patient_told）。
    """
    _change_status(request, RequestStatus.CONFIRMED, staff)
    request.gpis_appointment_id = gpis_appointment_id
    request.confirmed_date = confirmed_date
    request.confirmed_slot = confirmed_slot
    request.confirmed_doctor_id = confirmed_doctor_id
    request.confirm_message = confirm_message
    request.patient_told_at = None
    request.patient_told_by = None
    request.notify_problem = None
    session.flush()


def reopen_request(session: Session, request: AppointmentRequest) -> None:
    """拒绝、取消按错了：改回 PENDING（又算占用，A8），确认留下的资料全部清掉，重新确认时再点选 GPiS 的预约。"""
    if request.status not in (RequestStatus.REJECTED, RequestStatus.CANCELLED):
        raise InvalidTransition(f"{request.status} 不能改回 PENDING")
    request.status = RequestStatus.PENDING
    request.handled_by = None
    request.handled_at = None
    request.gpis_same_day_before = None      # GPiS 里可能已经有这个预约：自动确认重新看一次（之后多半只能员工按）
    request.gpis_appointment_id = None
    request.confirmed_date = None
    request.confirmed_slot = None
    request.confirmed_doctor_id = None
    request.confirm_message = None
    request.patient_told_at = None
    request.patient_told_by = None
    request.notify_problem = None
    session.flush()


def patient_notified(session: Session, request: AppointmentRequest) -> None:
    """系统经 WhatsApp 发出了确认消息。"""
    request.patient_told_at = func.now()
    request.patient_told_by = None
    request.notify_problem = None
    session.flush()


def notify_failed(session: Session, request: AppointmentRequest, problem: str) -> None:
    """系统没有发确认消息：留在「要通知」，写原因给员工看。"""
    request.notify_problem = problem
    session.flush()


def patient_told(session: Session, request: AppointmentRequest, staff: Staff) -> None:
    """员工自己通知了病人（Open in WhatsApp、手机），按 Patient told ✓。"""
    if request.status != RequestStatus.CONFIRMED or request.patient_told_at is not None:
        raise InvalidTransition("只有还没通知的 CONFIRMED 请求可以按 Patient told")
    request.patient_told_at = func.now()
    request.patient_told_by = staff.id
    session.flush()


def list_to_tell(session: Session) -> list[AppointmentRequest]:
    """「要通知」：确认了、病人还不知道的，先确认的排前面。"""
    return list(
        session.scalars(
            select(AppointmentRequest)
            .where(AppointmentRequest.status == RequestStatus.CONFIRMED, AppointmentRequest.patient_told_at.is_(None))
            .order_by(AppointmentRequest.handled_at, AppointmentRequest.id)
        )
    )


def reject_request(session: Session, request: AppointmentRequest, staff: Staff) -> None:
    _change_status(request, RequestStatus.REJECTED, staff)
    session.flush()


def cancel_request(session: Session, request: AppointmentRequest, staff: Staff | None = None) -> None:
    """病人取消。staff = None：病人自己在 WhatsApp 上取消（AI 处理）。"""
    _change_status(request, RequestStatus.CANCELLED, staff)
    session.flush()


def list_pending_requests(session: Session) -> list[AppointmentRequest]:
    """等员工确认的请求，先来的排前面。"""
    return list(
        session.scalars(
            select(AppointmentRequest)
            .where(AppointmentRequest.status == RequestStatus.PENDING)
            .order_by(AppointmentRequest.created_at, AppointmentRequest.id)
        )
    )


def held_requests(session: Session, day: date, doctor_id: str) -> list[HeldRequest]:
    """这天这位医生还在 PENDING 的请求：查空档时算占用（A8，architecture.md 11.6）。

    没有医生或没有时段的请求不算（不知道占哪一格）；CONFIRMED 之后不算（GPiS 里已经有了）。
    只回请求编号、时段、时长，没有病人资料。
    """
    rows = session.execute(
        select(AppointmentRequest.id, AppointmentRequest.preferred_slot, AppointmentRequest.duration_minutes)
        .where(
            AppointmentRequest.status == RequestStatus.PENDING,
            AppointmentRequest.preferred_date == day,
            AppointmentRequest.doctor_id == doctor_id.strip().upper(),
            AppointmentRequest.preferred_slot.is_not(None),
        )
        .order_by(AppointmentRequest.preferred_slot, AppointmentRequest.id)
    )
    return [HeldRequest(request_id, slot, minutes) for request_id, slot, minutes in rows]
