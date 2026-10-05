"""登录、登出、看自己是谁、改自己的密码。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_staff, end_all_sessions, end_session, hash_password, start_session, verify_password
from ..db.models import Staff, StaffRole
from ..db.session import get_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


class StaffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    name: str
    role: StaffRole
    active: bool


class LoginIn(BaseModel):
    username: str
    password: str


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/login", response_model=StaffOut)
def login(body: LoginIn, response: Response, session: Session = Depends(get_session)) -> Staff:
    staff = session.scalars(select(Staff).where(Staff.username == body.username.strip().lower())).one_or_none()
    # 用户名不对、密码不对、账号停用：都回一样的信息，不告诉别人是哪一个错
    if not verify_password(staff, body.password) or not staff.active:
        raise HTTPException(status_code=401, detail="Wrong username or password")
    start_session(session, staff, response)
    session.commit()
    return staff


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, session: Session = Depends(get_session)) -> None:
    end_session(session, request, response)
    session.commit()


@router.get("/me", response_model=StaffOut)
def me(staff: Staff = Depends(current_staff)) -> Staff:
    return staff


@router.post("/password", status_code=204)
def change_password(
    body: PasswordChangeIn,
    request: Request,
    staff: Staff = Depends(current_staff),
    session: Session = Depends(get_session),
) -> None:
    if not verify_password(staff, body.current_password):
        raise HTTPException(status_code=400, detail="Current password is wrong")
    try:
        staff.password_hash = hash_password(body.new_password)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    end_all_sessions(session, staff, keep=request)     # 其他电脑上的登录都要重新登录
    session.commit()
