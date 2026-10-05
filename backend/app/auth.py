"""员工登录和权限（Phase 4）。

- 密码用 Argon2 加密后才存（staff.password_hash），绝不存明文。
- 登录成功发一个 session cookie：HttpOnly（网页的 JavaScript 读不到）、SameSite=Strict
  （别的网站发来的请求不会带上它，防 CSRF），12 小时后失效。
- 每个请求都重新检查 session 和员工是不是还 active：员工停用后马上不能用。
- STAFF 处理对话和预约请求；只有 ADMIN 能改排班、疗程、假期、员工账号。
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import cookie_secure
from .db.models import Staff, StaffRole, StaffSession
from .db.session import get_session

COOKIE_NAME = "session"
SESSION_HOURS = 12
MIN_PASSWORD_LENGTH = 8

_hasher = PasswordHasher()
# 用户名不存在时也验证一次：回应时间一样，别人猜不出哪些用户名存在
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    return _hasher.hash(password)


def verify_password(staff: Staff | None, password: str) -> bool:
    stored = staff.password_hash if staff is not None and staff.password_hash else _DUMMY_HASH
    try:
        _hasher.verify(stored, password)
    except (VerificationError, InvalidHashError):
        return False
    return stored is not _DUMMY_HASH


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def start_session(session: Session, staff: Staff, response: Response) -> None:
    session.execute(delete(StaffSession).where(StaffSession.expires_at < _now()))   # 顺便清掉过期的
    token = secrets.token_urlsafe(32)
    session.add(StaffSession(
        staff_id=staff.id, token_hash=_token_hash(token), expires_at=_now() + timedelta(hours=SESSION_HOURS)
    ))
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_HOURS * 3600, path="/",
        httponly=True, samesite="strict", secure=cookie_secure(),
    )


def end_session(session: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        session.execute(delete(StaffSession).where(StaffSession.token_hash == _token_hash(token)))
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="strict", secure=cookie_secure())


def end_all_sessions(session: Session, staff: Staff, keep: Request | None = None) -> None:
    """登出这位员工的所有 session（改密码、被停用时）。keep：保留发出这个请求的 session。"""
    stmt = delete(StaffSession).where(StaffSession.staff_id == staff.id)
    token = keep.cookies.get(COOKIE_NAME) if keep is not None else None
    if token:
        stmt = stmt.where(StaffSession.token_hash != _token_hash(token))
    session.execute(stmt)


def current_staff(request: Request, session: Session = Depends(get_session)) -> Staff:
    """FastAPI dependency：要登录才能用。"""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        row = session.scalars(
            select(StaffSession).where(
                StaffSession.token_hash == _token_hash(token), StaffSession.expires_at > _now()
            )
        ).one_or_none()
        if row is not None and row.staff.active:
            return row.staff
    raise HTTPException(status_code=401, detail="Please log in")


def require_admin(staff: Staff = Depends(current_staff)) -> Staff:
    """FastAPI dependency：只有 ADMIN 能用。"""
    if staff.role != StaffRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only an admin can do this")
    return staff
