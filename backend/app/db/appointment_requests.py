"""预约请求：AI（或员工）建立 PENDING → 员工在 GPiS 录入 → CONFIRMED（D6）。

CONFIRMED 有两种（D70）：员工按确认（confirmed_by = STAFF），或系统每 3 分钟在 GPiS 找到了（SYSTEM，
app/request_matcher.py）。PENDING 的请求查空档时算占用（A8，pending_holds）。

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

from ..availability import PendingHold
from .models import AppointmentRequest, Conversation, Customer, Doctor, DoneBy, RequestStatus, Service, Staff

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
    # 先读 staff.id：读的时候可能要查数据库（autoflush），那时 status 改了一半会违反 CHECK
    staff_id = staff.id if staff else None
    request.status = new
    request.handled_by = staff_id
    request.handled_at = func.now()


def confirm_request(
    session: Session, request: AppointmentRequest, staff: Staff, gpis_appointment_id: int | None = None
) -> None:
    """员工确认（录入 GPiS）。gpis_appointment_id 可以不填：GPiS 画面不显示 AppointmentID。"""
    _change_status(request, RequestStatus.CONFIRMED, staff)
    request.confirmed_by = DoneBy.STAFF
    if gpis_appointment_id is not None:
        request.gpis_appointment_id = gpis_appointment_id
    session.flush()


def confirm_found_in_gpis(session: Session, request: AppointmentRequest, gpis_appointment_id: int) -> None:
    """系统在 GPiS 找到了这个预约（D70）：handled_by 空 = 系统。"""
    _change_status(request, RequestStatus.CONFIRMED, None)
    request.confirmed_by = DoneBy.SYSTEM
    request.gpis_appointment_id = gpis_appointment_id
    session.flush()


def mark_patient_notified(session: Session, request: AppointmentRequest, staff: Staff | None = None) -> None:
    """病人知道约好了：staff = None 是系统经 WhatsApp 发的，不然是员工自己通知后按 Patient told ✓。"""
    if request.status != RequestStatus.CONFIRMED:
        raise InvalidTransition(f"{request.status} 的请求不用通知")
    if request.patient_notified_at is not None:
        raise InvalidTransition("已经通知过了")
    staff_id = staff.id if staff else None
    request.patient_notified_at = func.now()
    request.patient_notified_by = DoneBy.STAFF if staff else DoneBy.SYSTEM
    request.patient_notified_staff_id = staff_id
    request.notify_problem = None
    session.flush()


def pending_holds(session: Session, day: date, doctor_id: str) -> list[PendingHold]:
    """这位医生这天还没录入 GPiS 的请求（A8）：查空档时算占用。

    只算有日期、时段、医生的；没有时段的（只说了哪一天）不知道占哪一格，不算。
    """
    rows = session.execute(
        select(AppointmentRequest.id, AppointmentRequest.preferred_slot, AppointmentRequest.duration_minutes)
        .where(
            AppointmentRequest.status == RequestStatus.PENDING,
            AppointmentRequest.preferred_date == day,
            AppointmentRequest.doctor_id == doctor_id.strip().upper(),
            AppointmentRequest.preferred_slot.is_not(None),
        )
        .order_by(AppointmentRequest.id)
    )
    return [PendingHold(request_id=r.id, slot=r.preferred_slot, duration_minutes=r.duration_minutes) for r in rows]


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
