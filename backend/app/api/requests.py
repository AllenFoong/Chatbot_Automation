"""预约请求：员工看待确认的请求，在 GPiS 录入后按确认；或拒绝、帮病人取消（D6）。"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_staff
from ..db import appointment_requests as reqs
from ..db.models import AppointmentRequest, RequestStatus, Staff
from ..db.session import get_session

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
    handled_by: int | None
    handled_at: datetime | None
    created_at: datetime


class ConfirmIn(BaseModel):
    gpis_appointment_id: int | None = Field(None, description="GPiS 的 AppointmentID；不知道就不填")


def _out(r: AppointmentRequest) -> RequestOut:
    return RequestOut(
        id=r.id, status=r.status,
        customer_id=r.customer_id, customer_name=r.customer.name, customer_phone=r.customer.phone,
        gpis_contact_id=r.customer.gpis_contact_id, conversation_id=r.conversation_id,
        service_code=r.service_code, service_name=r.service.name, doctor_id=r.doctor_id,
        preferred_date=r.preferred_date, preferred_slot=r.preferred_slot, duration_minutes=r.duration_minutes,
        notes=r.notes, group_id=r.group_id, gpis_appointment_id=r.gpis_appointment_id,
        handled_by=r.handled_by, handled_at=r.handled_at, created_at=r.created_at,
    )


@router.get("", response_model=list[RequestOut])
def list_requests(
    status: RequestStatus = Query(RequestStatus.PENDING),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[RequestOut]:
    """PENDING：先来的排前面（先处理）；其他状态：最近的排前面。"""
    order = (AppointmentRequest.created_at, AppointmentRequest.id)
    if status != RequestStatus.PENDING:
        order = tuple(o.desc() for o in order)
    stmt = (
        select(AppointmentRequest)
        .where(AppointmentRequest.status == status)
        .options(selectinload(AppointmentRequest.customer), selectinload(AppointmentRequest.service))
        .order_by(*order)
        .limit(limit)
    )
    return [_out(r) for r in session.scalars(stmt)]


def _change(session: Session, request_id: int, change) -> RequestOut:
    r = session.get(AppointmentRequest, request_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Request not found")
    try:
        change(r)
    except reqs.InvalidTransition as e:
        raise HTTPException(status_code=409, detail=f"A {r.status} request cannot be changed like this") from e
    session.commit()
    session.refresh(r)
    return _out(r)


@router.post("/{request_id}/confirm", response_model=RequestOut)
def confirm(
    request_id: int,
    body: ConfirmIn | None = None,
    staff: Staff = Depends(current_staff),
    session: Session = Depends(get_session),
) -> RequestOut:
    """员工已经在 GPiS 录入这个预约。"""
    gpis_id = body.gpis_appointment_id if body else None
    return _change(session, request_id, lambda r: reqs.confirm_request(session, r, staff, gpis_id))


@router.post("/{request_id}/reject", response_model=RequestOut)
def reject(
    request_id: int, staff: Staff = Depends(current_staff), session: Session = Depends(get_session)
) -> RequestOut:
    return _change(session, request_id, lambda r: reqs.reject_request(session, r, staff))


@router.post("/{request_id}/cancel", response_model=RequestOut)
def cancel(
    request_id: int, staff: Staff = Depends(current_staff), session: Session = Depends(get_session)
) -> RequestOut:
    """病人取消。已经确认的，员工也要在 GPiS 把预约改成 Canceled。"""
    return _change(session, request_id, lambda r: reqs.cancel_request(session, r, staff))
