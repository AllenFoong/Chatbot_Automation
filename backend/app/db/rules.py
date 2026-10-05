"""从 PostgreSQL 读出诊所设置，变成 availability.py 用的 ClinicRules。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clinic_rules import ClinicRules, DaySchedule, WeekSchedule
from .models import ClinicClosure, ClinicSettings, Doctor, DoctorLeave, DoctorSchedule, Service


class RulesNotConfigured(RuntimeError):
    pass


def load_clinic_rules(session: Session) -> ClinicRules:
    """每次都重新读：员工随时会改设置。离职（active = false）的医生当作不存在（UNKNOWN_DOCTOR）。"""
    settings = session.get(ClinicSettings, 1)
    if settings is None:
        raise RulesNotConfigured("数据库里还没有诊所设置：先执行 python -m app.db.seed")

    schedules: dict[str, WeekSchedule] = {}
    for s in session.scalars(select(DoctorSchedule).join(DoctorSchedule.doctor).where(Doctor.active)):
        schedules.setdefault(s.doctor_id, {})[s.weekday] = (
            DaySchedule(s.start_time, s.last_slot, s.break_start, s.break_end) if s.is_working else None
        )

    return ClinicRules(
        schedules=schedules,
        can_be_third=frozenset(session.scalars(select(Service.code).where(Service.active, Service.can_be_third))),
        max_per_slot=settings.max_per_slot,
        max_per_slot_for_ai=settings.max_per_slot_for_ai,
        clinic_contact_id=settings.clinic_contact_id,
        closures={c.closure_date: c.reason for c in session.scalars(select(ClinicClosure))},
        doctor_leaves=frozenset((v.doctor_id, v.leave_date) for v in session.scalars(select(DoctorLeave))),
    )
