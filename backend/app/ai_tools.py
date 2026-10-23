"""6a-3：AI 用的工具（architecture.md 11.4）。还不接 AI，都是普通的函数，用 pytest 测。

每个工具都照同样的三步：
1. 检查 AI 给的参数（AI 给的一律不信）。不对就回 {"error": "..."}：写清楚哪里错、正确的写法，
   AI 看了可以自己改，或者去问病人。程序不会停掉。
2. 资料由程序自己去拿（GPiS 的预约、PostgreSQL 的诊所设定和 PENDING 的请求），AI 碰不到。
3. 只回 AI 回复病人需要的最少资料：可以约的时间。别的病人的任何资料（预约编号、几个人、名字）都不回。

这一步（6a-3a）只有查空档的两个工具；找病人、原来的医生、建请求在 6a-3b。
"""

from __future__ import annotations

import functools
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .availability import check_available_slots as compute_day
from .clinic_rules import ClinicRules
from .db.appointment_requests import held_requests
from .db.models import Doctor, Service
from .db.rules import load_clinic_rules
from .gpis import AppointmentSource

log = logging.getLogger(__name__)

MAX_DAYS_AHEAD = 60     # 只约 60 天内（architecture.md 11.4）
SEARCH_DAYS = 14        # 往后找空档最多看 14 天
NEXT_DAYS = 3           # 往后找空档：找到 3 天就停

_DOCTOR_PREFIX = re.compile(r"^DR\.?\s*")


@dataclass
class ToolContext:
    """工具需要、但不由 AI 给的东西：数据库、GPiS、今天的日期（马来西亚时间，app.reminders.clinic_today）。"""

    session: Session
    gpis: AppointmentSource
    today: date


class ToolError(Exception):
    """AI 给的参数不对，或这个要求 AI 不能自己处理：讯息直接回给 AI（英文，AI 再用病人的语言说）。"""


# ---------- 检查 AI 给的参数 ----------

def _parse_date(value: str | None, ctx: ToolContext, name: str = "date") -> date:
    try:
        day = date.fromisoformat((value or "").strip())
    except ValueError:
        raise ToolError(f"{name} {value!r} is not a date. Use YYYY-MM-DD, for example "
                        f"{(ctx.today + timedelta(days=1)).isoformat()}. Today is {ctx.today.isoformat()}.") from None
    last = ctx.today + timedelta(days=MAX_DAYS_AHEAD)
    if day > last:
        raise ToolError(f"{day.isoformat()} is too far ahead: bookings are only taken until {last.isoformat()} "
                        f"({MAX_DAYS_AHEAD} days).")
    return day


def _bookable_date(value: str | None, ctx: ToolContext) -> date:
    """要约的那一天：明天到 60 天内（今天的空档要员工看，architecture.md 11.4）。"""
    day = _parse_date(value, ctx)
    if day <= ctx.today:
        raise ToolError(f"{day.isoformat()} is not after today ({ctx.today.isoformat()}). "
                        "Only tomorrow or later can be booked here; for today, hand over to staff.")
    return day


def _ai_service(session: Session, value: str | None) -> Service:
    """疗程代码要存在、还在用，而且 AI 能自己约（ai_can_book）。可能要 1 hour 的疗程由员工决定（D15）。"""
    code = (value or "").strip().upper()
    service = session.get(Service, code)
    if service is None or not service.active:
        codes = session.scalars(
            select(Service.code).where(Service.active, Service.ai_can_book, Service.may_need_1h.is_(False))
            .order_by(Service.code)
        )
        raise ToolError(f"Unknown treatment code {value!r}. Codes you can book: {', '.join(codes)}. "
                        "For any other treatment, hand over to staff.")
    if not service.ai_can_book or service.may_need_1h:
        raise ToolError(f"{service.code} ({service.name}) is booked by staff, not by you. Ask which days suit the "
                        "patient, then hand over to staff.")
    return service


def _doctors(session: Session, rules: ClinicRules, value: str | None) -> list[Doctor]:
    """不给医生 = 每一位有排班的医生。「Dr Phang」「phang」都当作 PHANG。"""
    doctors = list(session.scalars(
        select(Doctor).where(Doctor.active, Doctor.id.in_(rules.schedules)).order_by(Doctor.id)
    ))
    if value is None or not value.strip():
        return doctors
    wanted = _DOCTOR_PREFIX.sub("", value.strip().upper())
    match = [d for d in doctors if d.id == wanted]
    if not match:
        raise ToolError(f"Unknown doctor {value!r}. Doctors: {', '.join(d.id for d in doctors)}. "
                        "Leave the doctor out to see every doctor.")
    return match


# ---------- 一位医生、一天 ----------

def _not_working(rules: ClinicRules, day: date, doctor_id: str) -> str | None:
    """不用读 GPiS 就知道这天不能约的情况（和 availability.py 的 day_status 前几项一样）。"""
    if day in rules.closures:
        return f"clinic closed ({rules.closures[day]})"
    week = rules.schedules.get(doctor_id) or {}
    if week.get(day.isoweekday()) is None or (doctor_id, day) in rules.doctor_leaves:
        return "doctor not working this day"
    return None


_REASONS = {
    "OFFDAY_IN_GPIS": "doctor not working this day",
    "NEEDS_REVIEW": "staff need to check this day: if the patient wants this day, hand over to staff",
}


def _day_for_doctor(ctx: ToolContext, rules: ClinicRules, day: date, doctor: Doctor, service: Service) -> dict:
    """{"doctor", "name", "times"}，不能约就多一个 "not_available"（原因）。"""
    out: dict = {"doctor": doctor.id, "name": doctor.display_name, "times": []}
    reason = _not_working(rules, day, doctor.id)
    if reason:
        out["not_available"] = reason
        return out
    try:
        appointments = ctx.gpis.appointments_for(day, doctor.id)
    except Exception:
        # 连接字符串、driver 的错误只进日志，不给 AI（也就不会进对话）
        log.exception("AI 工具读 GPiS 失败")
        raise ToolError("The appointment book cannot be read right now. Tell the patient that staff will reply, "
                        "and hand over to staff.") from None
    r = compute_day(day, doctor.id, service.code, appointments, rules, held_requests(ctx.session, day, doctor.id))
    if r.day_status != "OK":
        out["not_available"] = _REASONS.get(r.day_status, "not available this day")
        return out
    # AI 能约的疗程都是 30 分钟（_ai_service 已经挡掉可能要 1 hour 的），所以看 can_30
    out["times"] = [s.time for s in r.slots if s.can_30]
    if not out["times"]:
        out["not_available"] = "fully booked"
    return out


def _tool(fn):
    """ToolError 变成 {"error": ...} 回给 AI；工具不会因为 AI 给错参数而停掉。"""
    @functools.wraps(fn)
    def run(*args, **kwargs) -> dict:
        try:
            return fn(*args, **kwargs)
        except ToolError as e:
            return {"error": str(e)}
    return run


# ---------- 工具 ----------

@_tool
def check_available_slots(ctx: ToolContext, date: str, service: str, doctor: str | None = None) -> dict:
    """某一天能约的时间。不给医生 = 每一位医生。

    回传：{"date", "weekday", "service", "doctors": [{"doctor", "name", "times": ["09:00", …], "not_available"?}]}
    """
    day = _bookable_date(date, ctx)
    svc = _ai_service(ctx.session, service)
    rules = load_clinic_rules(ctx.session)
    return {
        "date": day.isoformat(),
        "weekday": day.strftime("%A"),
        "service": svc.code,
        "doctors": [_day_for_doctor(ctx, rules, day, d, svc) for d in _doctors(ctx.session, rules, doctor)],
    }


@_tool
def find_next_available(ctx: ToolContext, service: str, doctor: str | None = None,
                        from_date: str | None = None) -> dict:
    """病人要的那天满了：从 from_date（不给 = 明天）往后找，最多看 14 天，找到 3 天有空的就停。

    回传：{"service", "searched_until", "days": [{"date", "weekday", "doctors": [{"doctor", "name", "times"}]}]}
    只列有空的日子和医生。一天都没有 → "days" 是空的，多一个 "message"。
    """
    svc = _ai_service(ctx.session, service)
    tomorrow = ctx.today + timedelta(days=1)
    start = max(_parse_date(from_date, ctx, "from_date"), tomorrow) if from_date else tomorrow
    rules = load_clinic_rules(ctx.session)
    doctors = _doctors(ctx.session, rules, doctor)
    last = min(start + timedelta(days=SEARCH_DAYS - 1), ctx.today + timedelta(days=MAX_DAYS_AHEAD))

    days: list[dict] = []
    day = start
    while day <= last and len(days) < NEXT_DAYS:
        free = [{"doctor": d["doctor"], "name": d["name"], "times": d["times"]}
                for d in (_day_for_doctor(ctx, rules, day, doc, svc) for doc in doctors) if d["times"]]
        if free:
            days.append({"date": day.isoformat(), "weekday": day.strftime("%A"), "doctors": free})
        day += timedelta(days=1)

    out: dict = {"service": svc.code, "searched_until": last.isoformat(), "days": days}
    if not days:
        out["message"] = (f"No free time from {start.isoformat()} to {last.isoformat()}. "
                          "Ask which days suit the patient, then hand over to staff.")
    return out


# ---------- 在终端试（开发电脑；印出来的就是 AI 会收到的，没有病人资料） ----------

def main(argv: list[str] | None = None) -> int:
    """python -m app.ai_tools check 2026-10-23 S+P [PHANG]
    python -m app.ai_tools next S+P [PHANG] [--from 2026-11-02]
    """
    import argparse
    import json

    from .db.session import new_session
    from .main import _default_reader
    from .reminders import clinic_today

    parser = argparse.ArgumentParser(prog="python -m app.ai_tools", description="Try the AI tools (6a-3a)")
    sub = parser.add_subparsers(dest="tool", required=True)
    check = sub.add_parser("check", help="check_available_slots")
    check.add_argument("date")
    check.add_argument("service")
    check.add_argument("doctor", nargs="?")
    nxt = sub.add_parser("next", help="find_next_available")
    nxt.add_argument("service")
    nxt.add_argument("doctor", nargs="?")
    nxt.add_argument("--from", dest="from_date")
    args = parser.parse_args(argv)

    with new_session() as session:
        ctx = ToolContext(session=session, gpis=_default_reader(), today=clinic_today())
        if args.tool == "check":
            out = check_available_slots(ctx, args.date, args.service, args.doctor)
        else:
            out = find_next_available(ctx, args.service, args.doctor, args.from_date)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 1 if "error" in out else 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
