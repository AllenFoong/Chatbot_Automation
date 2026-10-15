"""预约请求：AI（或员工）建立 PENDING → 员工确认后手动录入 GPiS（D6）。

状态只能这样改：
  PENDING   → CONFIRMED / REJECTED / CANCELLED
  CONFIRMED → CANCELLED（确认之后病人又取消：员工也要在 GPiS 改成 Canceled）
REJECTED、CANCELLED 之后不能再改。

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
    session: Session, request: AppointmentRequest, staff: Staff, gpis_appointment_id: int | None = None
) -> None:
    """员工确认（录入 GPiS）。gpis_appointment_id 可以不填：GPiS 画面不显示 AppointmentID。"""
    _change_status(request, RequestStatus.CONFIRMED, staff)
    if gpis_appointment_id is not None:
        request.gpis_appointment_id = gpis_appointment_id
    session.flush()


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
