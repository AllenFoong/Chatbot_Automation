"""6a-3：AI 用的工具（architecture.md 11.4）。还不接 AI，都是普通的函数，用 pytest 测。

每个工具都照同样的三步：
1. 检查 AI 给的参数（AI 给的一律不信）。不对就回 {"error": "..."}：写清楚哪里错、正确的写法，
   AI 看了可以自己改，或者去问病人。程序不会停掉。
2. 资料由程序自己去拿（GPiS 的预约、PostgreSQL 的诊所设定和 PENDING 的请求），AI 碰不到。
3. 只回 AI 回复病人需要的最少资料：可以约的时间。别的病人的任何资料（预约编号、几个人、名字）都不回。

6a-3a：查空档（check_available_slots、find_next_available，D78）。
6a-3b：找病人（find_patients）、多步骤疗程原来的医生（get_treatment_doctor）、建请求（create_appointment_request），D79。
找病人只能用这段 WhatsApp 对话的号码，AI 不能查别的号码。
"""

from __future__ import annotations

import functools
import logging
import re
from dataclasses import dataclass
from datetime import date, time, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .auto_confirm import has_treatment
from .availability import IGNORED_STATUSES
from .availability import check_available_slots as compute_day
from .clinic_rules import ClinicRules
from .confirm import may_send
from .db.appointment_requests import create_appointment_request as add_request
from .db.appointment_requests import held_requests
from .db.customers import create_customer, customers_booked_via, find_customers_by_phone
from .db.models import (
    AppointmentRequest,
    ClinicSettings,
    Conversation,
    Customer,
    Doctor,
    RequestStatus,
    Service,
    WaContact,
)
from .db.rules import load_clinic_rules
from .gpis import AppointmentSource, GpisPatient, PatientSource
from .reminders import _clean_name

log = logging.getLogger(__name__)

MAX_DAYS_AHEAD = 60     # 只约 60 天内（architecture.md 11.4）
SEARCH_DAYS = 14        # 往后找空档最多看 14 天
NEXT_DAYS = 3           # 往后找空档：找到 3 天就停

HISTORY_DAYS = 730      # 找原来的医生：看过去 2 年的预约
SLOT_LOCK = 642018      # 建请求时锁住「那天、那位医生」（PostgreSQL advisory lock；自动确认用 642017）
HIDDEN_NAME = "(name hidden: GPiS_Dev has real patients)"

_DOCTOR_PREFIX = re.compile(r"^DR\.?\s*")
_PATIENT_ID = re.compile(r"([GN])(\d{1,9})")
_TIME = re.compile(r"([01]?\d|2[0-3])[:.]([0-5]\d)")


@dataclass
class ToolContext:
    """工具需要、但不由 AI 给的东西：数据库、GPiS、今天的日期（马来西亚时间，app.reminders.clinic_today）。

    patients：找病人的来源（不给 = 用 gpis；REMINDER_SOURCE=demo 时是假资料）。
    conversation：这段 WhatsApp 对话。找病人用它的号码，建的请求挂在它下面。终端试的时候可以只给 phone。
    """

    session: Session
    gpis: AppointmentSource
    today: date
    patients: PatientSource | None = None
    conversation: Conversation | None = None
    phone: str | None = None


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


def _read_gpis(fn, *args):
    """读 GPiS。失败时连接字符串、driver 的错误只进日志，不给 AI（也就不会进对话）。"""
    try:
        return fn(*args)
    except Exception:
        log.exception("AI 工具读 GPiS 失败")
        raise ToolError("The appointment book cannot be read right now. Tell the patient that staff will reply, "
                        "and hand over to staff.") from None


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
    appointments = _read_gpis(ctx.gpis.appointments_for, day, doctor.id)
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


# ---------- 6a-3b：病人 ----------

@dataclass(frozen=True)
class _Patient:
    """find_patients 找到的一位：GPiS 的病人（contact_id）或本系统建的新病人（customer）。"""

    patient_id: str
    name: str
    contact_id: int | None = None
    customer: Customer | None = None


def _phone(ctx: ToolContext) -> str:
    if ctx.conversation is not None:
        return ctx.conversation.wa_contact.wa_phone
    if ctx.phone:
        return ctx.phone
    raise ToolError("This tool needs the WhatsApp conversation.")


def _patient_source(ctx: ToolContext) -> PatientSource:
    return ctx.patients if ctx.patients is not None else ctx.gpis


def _may_show_names(ctx: ToolContext) -> bool:
    """名字可以给 AI 吗？读 GPiS_Dev 时是真的病人，不能送到 AI 公司（规则 4、D44）；主机的 GPiS、假资料可以。"""
    return may_send(_patient_source(ctx))


def _patients(ctx: ToolContext) -> list[_Patient]:
    """这个号码的病人：GPiS 里用这个号码的（最近来过的在前），加上本系统建过、还没录入 GPiS 的新病人。"""
    phone = _phone(ctx)
    settings = ctx.session.get(ClinicSettings, 1)
    clinic_contact = settings.clinic_contact_id if settings else None
    found: list[GpisPatient] = _read_gpis(_patient_source(ctx).patients_for_phone, phone)
    out = [_Patient(f"G{p.contact_id}", _clean_name(p.name), contact_id=p.contact_id)
           for p in found if p.contact_id != clinic_contact]

    wa = ctx.conversation.wa_contact if ctx.conversation is not None else ctx.session.scalars(
        select(WaContact).where(WaContact.wa_phone == phone)).one_or_none()
    local = find_customers_by_phone(ctx.session, phone) + (customers_booked_via(ctx.session, wa.id) if wa else [])
    seen: set[int] = set()
    for c in sorted(local, key=lambda c: c.id):
        if c.gpis_contact_id is None and c.id not in seen:
            seen.add(c.id)
            out.append(_Patient(f"N{c.id}", c.name, customer=c))
    return out


def _resolve(ctx: ToolContext, patient_id: str | None) -> _Patient:
    """patient_id 一定要是这个号码的病人（AI 不能拿别人的 ID 来约）。"""
    pid = (patient_id or "").strip().upper()
    if not _PATIENT_ID.fullmatch(pid):
        raise ToolError(f"patient_id {patient_id!r} is not valid. Use a patient_id from find_patients, "
                        "for example G1234.")
    match = next((p for p in _patients(ctx) if p.patient_id == pid), None)
    if match is None:
        raise ToolError(f"{pid} is not a patient of this WhatsApp number. Call find_patients again.")
    return match


def _patient_out(ctx: ToolContext, p: _Patient) -> dict:
    hide = p.contact_id is not None and not _may_show_names(ctx)
    out = {"patient_id": p.patient_id, "name": HIDDEN_NAME if hide else p.name}
    if p.customer is not None:
        out["new_patient"] = True         # 员工还没录入 GPiS
    return out


def _treatment_doctor(ctx: ToolContext, p: _Patient, service: Service) -> Doctor | None:
    """多步骤疗程原来的医生（W9、D16）：过去 2 年到今天，同一类疗程（例 OR、ON、RB 都是 ORTHO）最近一次的医生。

    新病人、找不到、那位医生已经不在 → None（AI 要转员工）。
    """
    if p.contact_id is None:
        return None
    codes = list(ctx.session.scalars(select(Service.code).where(Service.treatment_group == service.treatment_group)))
    visits = _read_gpis(_patient_source(ctx).visits_of, p.contact_id,
                        ctx.today - timedelta(days=HISTORY_DAYS), ctx.today)
    same = [v for v in visits
            if v.doctor_id and (v.status or "").strip().lower() not in IGNORED_STATUSES
            and any(has_treatment(v.remarks, c) for c in codes)]
    if not same:
        return None
    doctor = ctx.session.get(Doctor, max(same, key=lambda v: v.day).doctor_id.strip().upper())
    return doctor if doctor is not None and doctor.active else None


def _parse_time(value: str | None) -> time:
    m = _TIME.fullmatch((value or "").strip())
    if not m:
        raise ToolError(f"time {value!r} is not valid. Use HH:MM (24 hours), for example 14:30.")
    return time(int(m.group(1)), int(m.group(2)))


def _new_patient_name(value: str) -> str:
    name = " ".join(value.split())
    if any(ch.isdigit() for ch in name):
        raise ToolError("new_patient_name must be the patient's name only (no IC, passport or phone number).")
    if not 2 <= len(name) <= 60:
        raise ToolError("new_patient_name must be 2 to 60 characters: the name the patient uses.")
    return name


@_tool
def find_patients(ctx: ToolContext) -> dict:
    """这个 WhatsApp 号码的病人（家人常共用一个号码，统计 B11）。没有参数：只能查这段对话的号码。

    回传：{"patients": [{"patient_id", "name", "new_patient"?}], "message"}。
    """
    patients = [_patient_out(ctx, p) for p in _patients(ctx)]
    if not patients:
        message = ("No patient uses this number: treat as a new patient. Ask only for the patient's name "
                   "(not the IC number); staff register the rest at the clinic.")
    else:
        message = ("Ask which of these patients the booking is for. If it is someone else, ask only for that "
                   "person's name and book as a new patient.")
    return {"patients": patients, "message": message}


@_tool
def get_treatment_doctor(ctx: ToolContext, patient_id: str, service: str) -> dict:
    """多步骤疗程（例 OR、RB、RETAINER）只约原来那位医生（D16）。不是多步骤的疗程 = 哪位医生都可以。

    回传：{"service", "doctor": "PHANG" | null, "name"?, "message"?}；找不到原来的医生 → error（转员工）。
    """
    svc = _ai_service(ctx.session, service)
    if not svc.multi_step:
        return {"service": svc.code, "doctor": None, "message": "Not a multi-step treatment: any doctor is fine."}
    p = _resolve(ctx, patient_id)
    doctor = _treatment_doctor(ctx, p, svc)
    if doctor is None:
        raise ToolError(f"No earlier {svc.treatment_group} visit with a current doctor was found for {p.patient_id}. "
                        "Ask which days suit the patient, then hand over to staff.")
    return {"service": svc.code, "doctor": doctor.id, "name": doctor.display_name}


@_tool
def create_appointment_request(ctx: ToolContext, service: str, doctor: str, date: str, time: str,
                               patient_id: str | None = None, new_patient_name: str | None = None) -> dict:
    """建一个 PENDING 的请求（员工录入 GPiS 后才算约好）。建之前再查一次那个时间还有没有空。

    病人二选一：patient_id（find_patients 给的）或 new_patient_name（新病人，只要名字）。
    回传：{"request_id", "status": "PENDING", "patient_id", "service", "doctor", "date", "weekday", "time", "message"}。
    """
    session = ctx.session
    try:
        return _create(ctx, service, doctor, date, time, patient_id, new_patient_name)
    except ToolError:
        session.rollback()          # 什么都不留；也放开锁
        raise


def _create(ctx: ToolContext, service: str, doctor: str, date_: str, time_: str,
            patient_id: str | None, new_patient_name: str | None) -> dict:
    session = ctx.session
    if ctx.conversation is None:
        raise ToolError("This tool needs the WhatsApp conversation.")
    day = _bookable_date(date_, ctx)
    svc = _ai_service(session, service)
    slot = _parse_time(time_)
    rules = load_clinic_rules(session)
    if doctor is None or not str(doctor).strip():
        raise ToolError("Choose a doctor: use check_available_slots to see each doctor's free times.")
    doc = _doctors(session, rules, doctor)[0]
    if bool(patient_id) == bool(new_patient_name and new_patient_name.strip()):
        raise ToolError("Give either patient_id (from find_patients) or new_patient_name, not both.")

    if patient_id:
        p = _resolve(ctx, patient_id)
    else:
        p = _Patient("", _new_patient_name(new_patient_name or ""))

    if svc.multi_step:
        need = _treatment_doctor(ctx, p, svc)
        if need is None:
            raise ToolError(f"{svc.code} is a follow-up visit, but no earlier {svc.treatment_group} visit was found "
                            "for this patient. Ask which days suit the patient, then hand over to staff.")
        if need.id != doc.id:
            raise ToolError(f"{svc.code} must be with the doctor who started the treatment: {need.id}. "
                            f"Check {need.id}'s free times.")

    # 同一个时间同时有两段对话在约：锁住这天这位医生，第二个要等第一个存好，再查一次就看得到它的请求
    session.execute(text("SELECT pg_advisory_xact_lock(:lock, hashtext(:key))"),
                    {"lock": SLOT_LOCK, "key": f"{day.isoformat()} {doc.id}"})

    customer = p.customer
    if customer is None and p.contact_id is not None:
        customer = session.scalars(select(Customer).where(Customer.gpis_contact_id == p.contact_id)).one_or_none()
    if customer is not None:
        pending = session.scalars(select(AppointmentRequest).where(
            AppointmentRequest.customer_id == customer.id,
            AppointmentRequest.status == RequestStatus.PENDING,
            AppointmentRequest.preferred_date == day,
        )).first()
        if pending is not None:
            when = pending.preferred_slot.strftime("%H:%M") if pending.preferred_slot else "no time yet"
            raise ToolError(f"This patient already has a request on {day.isoformat()} ({when}, request "
                            f"{pending.id}). Staff will confirm it; do not book the same day twice.")

    hhmm = slot.strftime("%H:%M")
    free = _day_for_doctor(ctx, rules, day, doc, svc)
    if hhmm not in free["times"]:
        others = ", ".join(free["times"]) or "none"
        raise ToolError(f"{hhmm} with {doc.id} on {day.isoformat()} is not free. Free times that day: {others}.")

    if customer is None:
        customer = create_customer(session, p.name, _phone(ctx), gpis_contact_id=p.contact_id)
    request = add_request(session, customer, svc.code, conversation=ctx.conversation, doctor_id=doc.id,
                          preferred_date=day, preferred_slot=slot, duration_minutes=30)
    session.commit()
    return {
        "request_id": request.id,
        "status": "PENDING",
        "patient_id": p.patient_id or f"N{customer.id}",
        "service": svc.code,
        "doctor": doc.id,
        "date": day.isoformat(),
        "weekday": day.strftime("%A"),
        "time": hhmm,
        "message": "Saved as a request. Tell the patient the clinic will confirm after staff enter it "
                   "(during opening hours).",
    }


# ---------- 在终端试（开发电脑；印出来的就是 AI 会收到的，没有病人资料） ----------

def main(argv: list[str] | None = None) -> int:
    """python -m app.ai_tools check 2026-10-23 S+P [PHANG]
    python -m app.ai_tools next S+P [PHANG] [--from 2026-11-02]
    python -m app.ai_tools patients 0123456789
    python -m app.ai_tools doctor 0123456789 G1234 OR
    python -m app.ai_tools book 0123456789 S+P PHANG 2026-10-30 10:00 (--patient G1234 | --new-name "Ali")

    找病人：REMINDER_SOURCE=demo 时用假资料；读 GPiS_Dev 时名字会藏起来（真的病人）。
    book 要那个号码有一段还没结束的对话（先用手机传消息给测试号码），会真的建一个 PENDING 的请求。
    """
    import argparse
    import json

    from .config import reminder_source_name
    from .db.conversations import get_open_conversation
    from .db.session import new_session
    from .main import _default_reader
    from .phone import normalize_phone
    from .reminder_demo import DemoReminderSource
    from .reminders import clinic_today

    parser = argparse.ArgumentParser(prog="python -m app.ai_tools", description="Try the AI tools (6a-3)")
    sub = parser.add_subparsers(dest="tool", required=True)
    check = sub.add_parser("check", help="check_available_slots")
    check.add_argument("date")
    check.add_argument("service")
    check.add_argument("doctor", nargs="?")
    nxt = sub.add_parser("next", help="find_next_available")
    nxt.add_argument("service")
    nxt.add_argument("doctor", nargs="?")
    nxt.add_argument("--from", dest="from_date")
    pat = sub.add_parser("patients", help="find_patients")
    pat.add_argument("phone")
    doc = sub.add_parser("doctor", help="get_treatment_doctor")
    doc.add_argument("phone")
    doc.add_argument("patient_id")
    doc.add_argument("service")
    book = sub.add_parser("book", help="create_appointment_request")
    book.add_argument("phone")
    book.add_argument("service")
    book.add_argument("doctor")
    book.add_argument("date")
    book.add_argument("time")
    who = book.add_mutually_exclusive_group(required=True)
    who.add_argument("--patient", dest="patient_id")
    who.add_argument("--new-name", dest="new_patient_name")
    args = parser.parse_args(argv)

    phone = None
    if args.tool in ("patients", "doctor", "book"):
        phone = normalize_phone(args.phone)
        if phone is None:
            print("That is not a phone number.")
            return 2

    reader = _default_reader()
    with new_session() as session:
        patients = DemoReminderSource.from_settings() if reminder_source_name() == "demo" else reader
        ctx = ToolContext(session=session, gpis=reader, today=clinic_today(), patients=patients, phone=phone)
        if args.tool == "check":
            out = check_available_slots(ctx, args.date, args.service, args.doctor)
        elif args.tool == "next":
            out = find_next_available(ctx, args.service, args.doctor, args.from_date)
        elif args.tool == "patients":
            out = find_patients(ctx)
        elif args.tool == "doctor":
            out = get_treatment_doctor(ctx, args.patient_id, args.service)
        else:
            wa = session.scalars(select(WaContact).where(WaContact.wa_phone == phone)).one_or_none()
            ctx.conversation = get_open_conversation(session, wa.id) if wa else None
            if ctx.conversation is None:
                print("No open conversation for that number: send a WhatsApp message to the test number first.")
                return 1
            out = create_appointment_request(ctx, args.service, args.doctor, args.date, args.time,
                                             args.patient_id, args.new_patient_name)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 1 if "error" in out else 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
