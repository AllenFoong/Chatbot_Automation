"""员工账号管理（只有 ADMIN）。员工离职改成 active = false（旧的记录还会指向他）。

删除（D75）：只有「在系统里没做过事」的账号可以删（例：建错、重复的）。回过消息、确认过请求、按过提醒、
负责过对话、标记过 NO WA 的账号删了，记录就不知道是谁做的 → 回 409，请改用停用。自己、最后一个 ADMIN 不能删。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import end_all_sessions, hash_password, require_admin
from ..db.models import (
    AppointmentRequest, Conversation, Message, Reminder, Staff, StaffRole, WaContact,
)
from ..db.session import get_session
from .auth import StaffOut

router = APIRouter(prefix="/api/staff", tags=["staff"], dependencies=[Depends(require_admin)])


class StaffIn(BaseModel):
    username: str
    name: str
    role: StaffRole = StaffRole.STAFF
    password: str


class StaffPatch(BaseModel):
    name: str | None = None
    role: StaffRole | None = None
    active: bool | None = None
    password: str | None = None      # ADMIN 帮员工重设密码


def _hash(password: str) -> str:
    try:
        return hash_password(password)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("", response_model=list[StaffOut])
def list_staff(session: Session = Depends(get_session)) -> list[Staff]:
    return list(session.scalars(select(Staff).order_by(Staff.username)))


@router.post("", response_model=StaffOut, status_code=201)
def add_staff(body: StaffIn, session: Session = Depends(get_session)) -> Staff:
    staff = Staff(
        username=body.username.strip().lower(), name=body.name.strip(), role=body.role,
        password_hash=_hash(body.password),
    )
    session.add(staff)
    session.commit()
    return staff


@router.patch("/{staff_id}", response_model=StaffOut)
def update_staff(staff_id: int, body: StaffPatch, session: Session = Depends(get_session)) -> Staff:
    staff = session.get(Staff, staff_id)
    if staff is None:
        raise HTTPException(status_code=404, detail="Staff not found")
    changes = body.model_dump(exclude_unset=True)

    # 至少要留一个 active 的 ADMIN，不然没有人能改设置
    loses_admin = staff.role == StaffRole.ADMIN and staff.active and (
        changes.get("role", StaffRole.ADMIN) != StaffRole.ADMIN or changes.get("active", True) is False
    )
    if loses_admin:
        other_admins = session.scalar(
            select(func.count()).select_from(Staff)
            .where(Staff.role == StaffRole.ADMIN, Staff.active, Staff.id != staff.id)
        )
        if not other_admins:
            raise HTTPException(status_code=409, detail="At least one active admin is required")

    password = changes.pop("password", None)
    if password is not None:
        staff.password_hash = _hash(password)
        end_all_sessions(session, staff)        # 重设密码后，要用新密码重新登录
    for field, value in changes.items():
        setattr(staff, field, value)
    if changes.get("active") is False:
        end_all_sessions(session, staff)
    session.commit()
    return staff


# 记着「是哪一位员工做的」的栏位（登录的 session 不算：删账号时一起删掉）
_STAFF_REFERENCES = (
    (Message.staff_id, "sent messages"),
    (Conversation.assigned_staff_id, "handled conversations"),
    (AppointmentRequest.handled_by, "handled appointment requests"),
    (AppointmentRequest.patient_told_by, "told patients about appointments"),
    (Reminder.staff_id, "sent reminders"),
    (WaContact.reminders_opt_out_staff_id, "marked NO WA numbers"),
)


@router.delete("/{staff_id}", status_code=204)
def delete_staff(staff_id: int, me: Staff = Depends(require_admin), session: Session = Depends(get_session)) -> Response:
    """删掉没用过的账号（建错、重复的）。用过的要停用，旧的记录才知道是谁做的。"""
    staff = session.get(Staff, staff_id)
    if staff is None:
        raise HTTPException(status_code=404, detail="Staff not found")
    if staff.id == me.id:
        raise HTTPException(status_code=409, detail="You cannot delete your own account")
    if staff.role == StaffRole.ADMIN and staff.active:
        other_admins = session.scalar(
            select(func.count()).select_from(Staff)
            .where(Staff.role == StaffRole.ADMIN, Staff.active, Staff.id != staff.id)
        )
        if not other_admins:
            raise HTTPException(status_code=409, detail="At least one active admin is required")
    used = [what for column, what in _STAFF_REFERENCES
            if session.scalar(select(column).where(column == staff.id).limit(1)) is not None]
    if used:
        raise HTTPException(
            status_code=409,
            detail=f"{staff.username} has {', '.join(used)}. Deactivate the account instead, so the history still "
                   "shows who did it.",
        )
    session.delete(staff)                         # 登录的 session 跟着删（ON DELETE CASCADE）
    session.commit()
    return Response(status_code=204)

