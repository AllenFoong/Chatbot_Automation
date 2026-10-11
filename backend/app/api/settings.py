"""诊所设置：医生、排班、疗程、休息日（假期管理）、医生请假、其他设置。

所有员工都能看；只有 ADMIN 能改（D14）。改了马上生效：/availability 每次都从数据库读设置。
数据库约束（时间在 30 分钟格上、每格上限 1–3 …）挡下的错误值，回 422。
"""

from __future__ import annotations

from datetime import date, time

import holidays
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from ..auth import current_staff, require_admin
from ..db.models import ClinicClosure, ClinicSettings, Doctor, DoctorLeave, DoctorSchedule, Service
from ..db.session import get_session

router = APIRouter(prefix="/api", tags=["settings"], dependencies=[Depends(current_staff)])
admin = [Depends(require_admin)]

# 公共假期：马来西亚全国 + Johor 州（W1、W14）
HOLIDAY_COUNTRY, HOLIDAY_STATE = "MY", "JHR"

# 诊所只休这几种（D61）：holidays 套件的英文名字 → 名单上显示的名字（诊所的写法）。
# 其他假期（Wesak、Hari Raya Haji …）照常营业；替代假（"(observed)"、"(additional holiday)"）也不休（W56）
CLINIC_HOLIDAYS = {
    "Chinese New Year": "Chinese New Year",
    "Chinese New Year (Second Day)": "Chinese New Year Holiday",
    "Eid al-Fitr": "Hari Raya Aidilfitri",
    "Eid al-Fitr (Second Day)": "Hari Raya Aidilfitri Holiday",
    "Birthday of the Sultan of Johor": "Sultan of Johor's Birthday",
    "Labor Day": "Labour Day",
    "National Day": "Merdeka Day",
    "Malaysia Day": "Malaysia Day",
    "Diwali": "Deepavali",
    "Christmas Day": "Christmas Day",
}
# Johor 没有放、诊所自己休的固定日子（W57：2027 年的名单有 New Year's Day）
CLINIC_FIXED_DAYS = {(1, 1): "New Year's Day"}


def clinic_holidays(year: int) -> dict[date, str]:
    """那一年诊所休的公共假期。回教节日的日期是套件预估的，要员工核对。"""
    found = holidays.country_holidays(HOLIDAY_COUNTRY, subdiv=HOLIDAY_STATE, years=year, language="en_US")
    days = {day: CLINIC_HOLIDAYS[name] for day, name in found.items() if name in CLINIC_HOLIDAYS}
    days.update({date(year, m, d): name for (m, d), name in CLINIC_FIXED_DAYS.items()})
    return dict(sorted(days.items()))


class _Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- 医生、排班 ----------

class DoctorOut(_Orm):
    id: str
    display_name: str
    remark_tag: str | None
    active: bool


class DoctorIn(BaseModel):
    id: str = Field(description="= GPiS 的 DoctorID")
    display_name: str
    remark_tag: str | None = None


class DoctorPatch(BaseModel):
    display_name: str | None = None
    remark_tag: str | None = None
    active: bool | None = None


class DayIn(_Orm):
    weekday: int = Field(ge=1, le=7, description="1 = Monday … 7 = Sunday")
    is_working: bool
    start_time: time | None = None
    last_slot: time | None = None
    break_start: time | None = None
    break_end: time | None = None


def _doctor(session: Session, doctor_id: str) -> Doctor:
    d = session.get(Doctor, doctor_id.strip().upper())
    if d is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return d


@router.get("/doctors", response_model=list[DoctorOut])
def list_doctors(session: Session = Depends(get_session)) -> list[Doctor]:
    return list(session.scalars(select(Doctor).order_by(Doctor.id)))


@router.post("/doctors", response_model=DoctorOut, status_code=201, dependencies=admin)
def add_doctor(body: DoctorIn, session: Session = Depends(get_session)) -> Doctor:
    """新医生：先建 7 天都休息的排班，再用 PUT /schedule 设上班时间。"""
    doctor = Doctor(id=body.id.strip().upper(), display_name=body.display_name.strip(), remark_tag=body.remark_tag)
    doctor.schedules = [DoctorSchedule(weekday=wd, is_working=False) for wd in range(1, 8)]
    session.add(doctor)
    session.commit()
    return doctor


@router.patch("/doctors/{doctor_id}", response_model=DoctorOut, dependencies=admin)
def update_doctor(doctor_id: str, body: DoctorPatch, session: Session = Depends(get_session)) -> Doctor:
    """离职的医生改成 active = false，不要删除。"""
    d = _doctor(session, doctor_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(d, field, value)
    session.commit()
    return d


@router.get("/doctors/{doctor_id}/schedule", response_model=list[DayIn])
def get_schedule(doctor_id: str, session: Session = Depends(get_session)) -> list[DoctorSchedule]:
    return sorted(_doctor(session, doctor_id).schedules, key=lambda s: s.weekday)


@router.put("/doctors/{doctor_id}/schedule", response_model=list[DayIn], dependencies=admin)
def set_schedule(doctor_id: str, days: list[DayIn], session: Session = Depends(get_session)) -> list[DoctorSchedule]:
    """一次送 7 天（星期一到日）。不上班的那天，时间都留空。"""
    d = _doctor(session, doctor_id)
    if sorted(day.weekday for day in days) != list(range(1, 8)):
        raise HTTPException(status_code=422, detail="Send exactly one entry for each weekday 1-7")
    existing = {s.weekday: s for s in d.schedules}
    for day in days:
        row = existing.get(day.weekday)
        if row is None:
            row = DoctorSchedule(doctor_id=d.id, weekday=day.weekday)
            session.add(row)
        values = day.model_dump()
        if not day.is_working:     # 休息的日子不留时间，免得以后看了以为有上班
            values.update(start_time=None, last_slot=None, break_start=None, break_end=None)
        for field, value in values.items():
            setattr(row, field, value)
    session.commit()
    return get_schedule(doctor_id, session)


# ---------- 疗程 ----------

class ServiceOut(_Orm):
    code: str
    name: str
    can_be_third: bool
    may_need_1h: bool
    ai_can_book: bool
    treatment_group: str | None
    active: bool


class ServiceIn(BaseModel):
    code: str
    name: str
    can_be_third: bool = False
    may_need_1h: bool = False
    ai_can_book: bool = False
    treatment_group: str | None = None


class ServicePatch(BaseModel):
    name: str | None = None
    can_be_third: bool | None = None
    may_need_1h: bool | None = None
    ai_can_book: bool | None = None
    treatment_group: str | None = None
    active: bool | None = None


@router.get("/services", response_model=list[ServiceOut])
def list_services(session: Session = Depends(get_session)) -> list[Service]:
    return list(session.scalars(select(Service).order_by(Service.code)))


@router.post("/services", response_model=ServiceOut, status_code=201, dependencies=admin)
def add_service(body: ServiceIn, session: Session = Depends(get_session)) -> Service:
    service = Service(**{**body.model_dump(), "code": body.code.strip().upper(), "name": body.name.strip()})
    session.add(service)
    session.commit()
    return service


# {code:path}：疗程代码里有 /（例 C/UP）
@router.patch("/services/{code:path}", response_model=ServiceOut, dependencies=admin)
def update_service(code: str, body: ServicePatch, session: Session = Depends(get_session)) -> Service:
    """不再提供的疗程改成 active = false，不要删除（旧的预约请求还会用到）。"""
    s = session.get(Service, code.strip().upper())
    if s is None:
        raise HTTPException(status_code=404, detail="Service not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(s, field, value)
    session.commit()
    return s


# ---------- 休息日（假期管理） ----------

class ClosureOut(_Orm):
    closure_date: date
    reason: str


class HolidayImportIn(BaseModel):
    year: int = Field(ge=2020, le=2100)


class HolidayImportOut(BaseModel):
    added: list[ClosureOut]
    already_there: int


@router.get("/closures", response_model=list[ClosureOut])
def list_closures(
    year: int | None = Query(None, description="不填 = 今天以后的"), session: Session = Depends(get_session)
) -> list[ClinicClosure]:
    stmt = select(ClinicClosure).order_by(ClinicClosure.closure_date)
    if year is None:
        stmt = stmt.where(ClinicClosure.closure_date >= date.today())
    else:
        stmt = stmt.where(extract("year", ClinicClosure.closure_date) == year)
    return list(session.scalars(stmt))


@router.post("/closures", response_model=ClosureOut, status_code=201, dependencies=admin)
def add_closure(body: ClosureOut, session: Session = Depends(get_session)) -> ClinicClosure:
    """诊所自己加的休息日，例如农历新年多休的日子。"""
    closure = ClinicClosure(closure_date=body.closure_date, reason=body.reason.strip())
    session.add(closure)
    session.commit()
    return closure


@router.delete("/closures/{closure_date}", status_code=204, dependencies=admin)
def delete_closure(closure_date: date, session: Session = Depends(get_session)) -> Response:
    closure = session.get(ClinicClosure, closure_date)
    if closure is None:
        raise HTTPException(status_code=404, detail="No closure on this date")
    session.delete(closure)
    session.commit()
    return Response(status_code=204)


@router.post("/closures/import-holidays", response_model=HolidayImportOut, dependencies=admin)
def import_holidays(body: HolidayImportIn, session: Session = Depends(get_session)) -> HolidayImportOut:
    """预填一年诊所会休的公共假期（Python holidays 套件，全国 + Johor，只取 CLINIC_HOLIDAYS 那 10 种，D61）。
    已经有的日子不动。

    回教节日的日期可能是预估的，农历新年诊所多休的日子也不会在里面：导入后要员工核对、补上（W14）。
    """
    existing = set(session.scalars(
        select(ClinicClosure.closure_date).where(extract("year", ClinicClosure.closure_date) == body.year)
    ))
    found = clinic_holidays(body.year)
    added = []
    for day, name in found.items():
        if day not in existing:
            closure = ClinicClosure(closure_date=day, reason=name[:100])
            session.add(closure)
            added.append(closure)
    session.commit()
    return HolidayImportOut(
        added=[ClosureOut.model_validate(c) for c in added],
        already_there=len(found) - len(added),
    )


# ---------- 医生请假 ----------

class LeaveOut(_Orm):
    doctor_id: str
    leave_date: date
    reason: str | None = None


@router.get("/leaves", response_model=list[LeaveOut])
def list_leaves(
    from_date: date | None = Query(None, description="不填 = 今天"), session: Session = Depends(get_session)
) -> list[DoctorLeave]:
    return list(session.scalars(
        select(DoctorLeave)
        .where(DoctorLeave.leave_date >= (from_date or date.today()))
        .order_by(DoctorLeave.leave_date, DoctorLeave.doctor_id)
    ))


@router.post("/leaves", response_model=LeaveOut, status_code=201, dependencies=admin)
def add_leave(body: LeaveOut, session: Session = Depends(get_session)) -> DoctorLeave:
    leave = DoctorLeave(
        doctor_id=_doctor(session, body.doctor_id).id, leave_date=body.leave_date, reason=body.reason
    )
    session.add(leave)
    session.commit()
    return leave


@router.delete("/leaves/{doctor_id}/{leave_date}", status_code=204, dependencies=admin)
def delete_leave(doctor_id: str, leave_date: date, session: Session = Depends(get_session)) -> Response:
    leave = session.get(DoctorLeave, (doctor_id.strip().upper(), leave_date))
    if leave is None:
        raise HTTPException(status_code=404, detail="No leave on this date")
    session.delete(leave)
    session.commit()
    return Response(status_code=204)


# ---------- 其他设置 ----------

class SettingsOut(_Orm):
    max_per_slot: int
    max_per_slot_for_ai: int
    clinic_contact_id: int


class SettingsPatch(BaseModel):
    max_per_slot: int | None = None
    max_per_slot_for_ai: int | None = None
    clinic_contact_id: int | None = None


def _settings(session: Session) -> ClinicSettings:
    s = session.get(ClinicSettings, 1)
    if s is None:
        raise HTTPException(status_code=503, detail="Clinic settings are missing: run python -m app.db.seed")
    return s


@router.get("/settings", response_model=SettingsOut)
def get_clinic_settings(session: Session = Depends(get_session)) -> ClinicSettings:
    return _settings(session)


@router.patch("/settings", response_model=SettingsOut, dependencies=admin)
def update_clinic_settings(body: SettingsPatch, session: Session = Depends(get_session)) -> ClinicSettings:
    s = _settings(session)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(s, field, value)
    session.commit()
    return s
