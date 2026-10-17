"""FastAPI 入口。启动：在 backend/ 里执行 `uvicorn app.main:app --reload`，打开 http://127.0.0.1:8000/docs"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import date
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from . import auto_confirm
from .api import auth as auth_api
from .api import conversations, reminders, requests, settings, staff
from .availability import HeldRequest, check_available_slots
from .clinic_rules import ClinicRules
from .config import get_settings
from .db.appointment_requests import held_requests
from .db.rules import RulesNotConfigured, load_clinic_rules
from .db.session import get_session
from .frontend_files import frontend_dist, mount_frontend
from .gpis import AppointmentSource, GpisReader, WrongDatabaseError

log = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Admin API 开着的时候，背景每 3 分钟跑一次自动确认（只有 Settings 打开了才真的做事，D71 ②）。

    AUTO_CONFIRM_LOOP=off 可以关掉这个背景（测试用）。webhook 小程序（webhook_main.py）没有这个背景。
    """
    loop = None
    if os.environ.get("AUTO_CONFIRM_LOOP", "on").strip().lower() != "off":
        loop = auto_confirm.Loop()
        loop.start()
    yield
    if loop is not None:
        loop.stop()


app = FastAPI(title="Chatbot_Automation API", version="0.6.0", lifespan=lifespan)
for module in (auth_api, conversations, reminders, requests, settings, staff):
    app.include_router(module.router)


@app.middleware("http")
async def api_not_cached(request: Request, call_next):
    """/api 的回应有病人名字、号码：浏览器不要存进硬盘的快取（A10、D67）。网页本身（frontend/dist）照常快取。"""
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(IntegrityError)
def database_rule_violated(request: Request, exc: IntegrityError) -> JSONResponse:
    """数据库约束挡下的资料（重复、违反 CHECK、找不到对应的医生 …）：回 409 / 422，告诉是哪一条规则。"""
    sqlstate = getattr(exc.orig, "sqlstate", None)
    rule = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if sqlstate == "23505":
        return JSONResponse(status_code=409, content={"detail": "Already exists", "rule": rule})
    return JSONResponse(status_code=422, content={"detail": "Rejected by a database rule", "rule": rule})


class SlotOut(BaseModel):
    time: str
    kind: str
    booked: int               # GPiS 的病人 + 本系统 PENDING 的请求
    requests: int             # booked 里面有几个是请求
    cap: int | None
    remaining: int
    can_30: bool
    can_60: bool


class AppointmentOut(BaseModel):
    appointment_id: int
    time_slot: str | None
    status: str | None
    dur_slots: int
    is_placeholder: bool
    is_off_day: bool
    hour_unparsed: bool
    occupies: bool


class HeldRequestOut(BaseModel):
    request_id: int
    time: str
    dur_slots: int


class AvailabilityOut(BaseModel):
    date: date
    weekday: str
    doctor: str
    service: str
    day_status: str
    note: str | None
    bookable: bool
    patients: int             # GPiS 里算病人的预约（和 SQL 一样）
    requests: int             # 本系统 PENDING 的请求，算进了 booked（A8）
    available_30: list[str]
    available_60: list[str]
    slots: list[SlotOut]
    appointments: list[AppointmentOut] | None = None
    held_requests: list[HeldRequestOut] | None = None


@lru_cache
def _default_reader() -> GpisReader:
    s = get_settings()
    return GpisReader(s.gpis_connection_string, s.gpis_expected_database)


def get_appointment_source() -> AppointmentSource:
    return _default_reader()


def get_rules(session: Session = Depends(get_session)) -> ClinicRules:
    """诊所设置每次都从 PostgreSQL 读：员工改了马上生效。"""
    try:
        return load_clinic_rules(session)
    except RulesNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except SQLAlchemyError as e:  # 不把连接字符串或 driver 的详细错误回给调用方
        log.exception("读取本系统设置失败")
        raise HTTPException(status_code=503, detail="读取本系统设置失败，请看服务器日志") from e


HeldRequestReader = Callable[[date, str], list[HeldRequest]]


def get_held_requests(session: Session = Depends(get_session)) -> HeldRequestReader:
    """本系统还在 PENDING 的请求（A8）：从 PostgreSQL 读。"""
    return lambda day, doctor: held_requests(session, day, doctor)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/availability", response_model=AvailabilityOut)
def availability(
    date_: date = Query(..., alias="date", description="日期，例：2026-10-09"),
    doctor: str = Query(..., description="PHANG / GOH"),
    service: str = Query(..., description="疗程代码，例：S+P、C/UP、OR"),
    debug: bool = Query(False, description="加上每条预约怎么被解读（只有 ID，没有名字和 Remarks）"),
    requests: bool = Query(
        True,
        description="把本系统还没录入 GPiS 的请求（PENDING）也算占用（A8）；false = 只看 GPiS，和 sql/check_available_slots.sql 对照用",
    ),
    source: AppointmentSource = Depends(get_appointment_source),
    rules: ClinicRules = Depends(get_rules),
    read_held: HeldRequestReader = Depends(get_held_requests),
) -> AvailabilityOut:
    try:
        rows = source.appointments_for(date_, doctor)
    except WrongDatabaseError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:  # 不把连接字符串或 driver 的详细错误回给调用方
        log.exception("读取 GPiS 失败")
        raise HTTPException(status_code=503, detail="读取 GPiS 失败，请看服务器日志") from e

    held: list[HeldRequest] = []
    if requests:
        try:
            held = read_held(date_, doctor)
        except SQLAlchemyError as e:
            log.exception("读取本系统的预约请求失败")
            raise HTTPException(status_code=503, detail="读取本系统的预约请求失败，请看服务器日志") from e

    r = check_available_slots(date_, doctor, service, rows, rules, held)
    return AvailabilityOut(
        date=r.date,
        weekday=r.weekday,
        doctor=r.doctor,
        service=r.service,
        day_status=r.day_status,
        note=r.note,
        bookable=r.bookable,
        patients=r.patients,
        requests=r.requests,
        available_30=[s.time for s in r.slots if s.can_30],
        available_60=[s.time for s in r.slots if s.can_60],
        slots=[SlotOut(**s.__dict__) for s in r.slots],
        appointments=[
            AppointmentOut(
                appointment_id=a.appointment_id,
                time_slot=a.time_slot,
                status=a.status,
                dur_slots=a.dur_slots,
                is_placeholder=a.is_placeholder,
                is_off_day=a.is_off_day,
                hour_unparsed=a.hour_unparsed,
                occupies=a.occupies,
            )
            for a in r.appointments
        ]
        if debug
        else None,
        held_requests=[
            HeldRequestOut(request_id=h.request_id, time=h.slot.strftime("%H:%M"), dur_slots=h.dur_slots)
            for h in r.held_requests
        ]
        if debug
        else None,
    )


# 上线（电脑 B）：同一个网址提供网页（D62）。放在最后：上面的 API 路由先配对
_dist = frontend_dist()
if _dist is not None:
    mount_frontend(app, _dist)
