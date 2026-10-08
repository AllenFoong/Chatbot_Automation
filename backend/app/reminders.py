"""预约提醒的名单（Phase 5b，docs/architecture.md 第 8 节）。

这里只做计算，不连接数据库：输入是 GPiS 那几天的预约（gpis.py 读出）和诊所设置，
输出是给员工看的名单：要提醒的（Ready）、要员工看的（Needs staff）、不是预约的（只算数量）。

- 沿用空档的判断（D41）：取消、OFF DAY、00:00 不是预约；诊所联系人、状态不明的交给员工。
- 不确定的不自动发，交给员工看，写明原因（画面是英文，D24）。
- 同一个号码、同一天的预约合成一条：NAME: A & B（D49）。
- 要等技工所的预约，Remarks 后面要有 *C 才发（D50、D51）。
- Remarks 只在内存里判断 OFF DAY、*C，不会出现在输出里（D44）。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
from typing import Protocol

from .availability import IGNORED_STATUSES, SLOT_MINUTES, normalize_remarks, parse_slot
from .clinic_rules import ClinicRules, DaySchedule
from .phone import normalize_phone

# 马来西亚没有夏令时间，固定 UTC+8（不用 zoneinfo：Windows 没有装 tzdata 会找不到时区）
CLINIC_TZ = timezone(timedelta(hours=8))

REMINDABLE_STATUSES = {"confirmed", "closed"}   # 将来的日期只有 Confirmed（B13）；以前的日子是 Closed
MAX_LINES_PER_MESSAGE = 5
MAX_DAYS_AHEAD = 14                              # 连休再长，也只往后找两个星期

# 要等技工所的代码（W39、W47）：Remarks 后面要有 *C = 东西已经送到诊所
_LAB_WORK = re.compile(
    r"(?<![A-Z])(?:ISSUE\s*(?:CROWN|BRIDGE|IMPLANT|DENTURE|C|B)|MMR|TRY\s*-?\s*IN|VENEERS?)(?![A-Z])",
    re.IGNORECASE,
)
# 一定写成 *C（D51）：大写 C 紧跟在 * 后面，后面不能再接字母
_ARRIVED = re.compile(r"\*C(?![A-Za-z])")


@dataclass(frozen=True)
class ReminderAppointment:
    """从 GPiS 读出的一条预约（提醒要用的栏位；没有 NRIC、地址）。"""

    appointment_id: int
    appointment_date: date
    time_slot: str | None
    doctor_id: str | None
    status: str | None
    contact_id: int | None
    contact_name: str | None
    hp_no: str | None
    remarks: str | None


class ReminderSource(Protocol):
    label: str            # 画面上显示资料从哪里来，例 "GPiS_Dev"、"Demo data"
    is_production: bool   # True = 读的是主机的 GPiS；只有这时才能打开真的病人的 WhatsApp（D54）

    def reminder_appointments(self, first: date, last: date) -> list[ReminderAppointment]: ...


class PhoneKind(StrEnum):
    MY_MOBILE = "MY_MOBILE"
    SG_MOBILE = "SG_MOBILE"
    OTHER_COUNTRY = "OTHER_COUNTRY"
    LANDLINE = "LANDLINE"
    MISSING = "MISSING"          # 没有号码，或看不懂


SENDABLE = {PhoneKind.MY_MOBILE, PhoneKind.SG_MOBILE, PhoneKind.OTHER_COUNTRY}


def phone_kind(phone: str | None) -> PhoneKind:
    """phone 是 normalize_phone 的结果。WhatsApp 只能发手机：马来西亚 601…，新加坡 658… / 659…"""
    if not phone:
        return PhoneKind.MISSING
    if phone.startswith("60"):
        return PhoneKind.MY_MOBILE if phone.startswith("601") else PhoneKind.LANDLINE
    if phone.startswith("65"):
        return PhoneKind.SG_MOBILE if phone[2:3] in ("8", "9") else PhoneKind.LANDLINE
    return PhoneKind.OTHER_COUNTRY


def lab_work_not_arrived(remarks: str | None) -> bool:
    """有要等技工所的代码，但后面没有 *C（D50、D51）。只认 *C 在代码后面。"""
    r = remarks or ""
    m = _LAB_WORK.search(r)
    return m is not None and _ARRIVED.search(r, m.end()) is None


def clinic_today(now: datetime | None = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(CLINIC_TZ).date()


def reminder_dates(today: date, closures: dict[date, str] | set[date]) -> list[date]:
    """今天要提醒哪几天：从明天到下一个营业日（包括）。

    平常就是明天；明天是公共假期的话，假期那天没有人发，所以今天连后天的一起发（W34）。
    """
    dates: list[date] = []
    d = today + timedelta(days=1)
    while len(dates) < MAX_DAYS_AHEAD:
        dates.append(d)
        if d not in closures:
            break
        d += timedelta(days=1)
    return dates


@dataclass(frozen=True)
class ReminderText:
    """提醒里诊所、分行的名字：放在 backend/.env，仓库里不写（D47、8.5）。"""

    clinic_name: str = "<诊所名>"
    clinic_name_en: str = "<Clinic name>"
    branch: str = "<分行名>"


@dataclass(frozen=True)
class ReminderLine:
    """名单上的一行：一位病人的一个预约（GPiS 里重复的记录合成一行）。"""

    appointment_ids: tuple[int, ...]
    day: date
    slot: time | None
    doctor_id: str
    patient_name: str
    status: str | None
    problems: tuple[str, ...]


@dataclass(frozen=True)
class ReminderGroup:
    """发给一个号码的一条提醒（同一天）。没有号码的病人各自一组。"""

    day: date
    phone: str | None
    phone_kind: PhoneKind
    lines: tuple[ReminderLine, ...]
    problems: tuple[str, ...]      # 这个号码的问题 + 每一行的问题（不重复）
    message: str | None            # 能发的号码才有

    @property
    def ready(self) -> bool:
        return not self.problems


@dataclass(frozen=True)
class ReminderList:
    dates: tuple[date, ...]
    ready: tuple[ReminderGroup, ...]
    needs_staff: tuple[ReminderGroup, ...]
    not_appointments: tuple[tuple[str, int], ...]   # (原因, 几条)


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _outside_hours(slot: int, schedule: DaySchedule) -> bool:
    """比上班早，或比最后一格晚超过一格（17:00 这种员工破例排的照常提醒；凌晨的是打错）。"""
    return slot < _minutes(schedule.start) or slot > _minutes(schedule.last_slot) + SLOT_MINUTES


def _clean_name(name: str | None) -> str:
    return " ".join((name or "").split()).upper()


def _problems(a: ReminderAppointment, slot: int | None, rules: ClinicRules,
              offday_doctors: set[tuple[date, str]]) -> list[str]:
    day, doctor, status = a.appointment_date, (a.doctor_id or "").strip().upper(), (a.status or "").strip()
    problems: list[str] = []
    if a.contact_id == rules.clinic_contact_id:
        problems.append("Booked under the clinic's own contact")
    elif not _clean_name(a.contact_name):
        problems.append("No patient name in GPiS")
    if status.lower() not in REMINDABLE_STATUSES:
        problems.append(f"Status is {status or 'empty'}")
    if slot is None:
        problems.append("Unreadable time slot")
    if day in rules.closures:
        problems.append(f"Clinic is closed that day ({rules.closures[day]})")
    week = rules.schedules.get(doctor)
    if week is None:
        problems.append(f"{doctor or 'No doctor'} is not an active doctor")
    else:
        schedule = week.get(day.isoweekday())
        if schedule is None:
            problems.append(f"Dr {doctor} does not work on {day:%A}")
        elif slot is not None and _outside_hours(slot, schedule):
            problems.append("Time is outside working hours")
    if (doctor, day) in rules.doctor_leaves:
        problems.append(f"Dr {doctor} is on leave")
    if (day, doctor) in offday_doctors:
        problems.append(f"GPiS has an OFF DAY record for Dr {doctor}")
    if lab_work_not_arrived(a.remarks):
        problems.append("Lab work not marked as arrived (*C)")
    return problems


def _join(values: list[str]) -> str:
    """全部一样就只写一次，不一样就照名字的顺序用 & 连起来（D49）。"""
    return values[0] if len(set(values)) == 1 else " & ".join(values)


def _time_12h(t: time) -> str:
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def render_message(lines: tuple[ReminderLine, ...], doctor_names: dict[str, str], text: ReminderText) -> str:
    """诊所现在用的原文（W32），英文那段改成写日期（W45）。和以后送审的模板一样（8.5）。"""
    day = lines[0].day
    name = _join([ln.patient_name for ln in lines])
    when = _join([_time_12h(ln.slot) if ln.slot else "?" for ln in lines])
    doctor = _join([f"DR {doctor_names.get(ln.doctor_id, ln.doctor_id).upper()}" for ln in lines])
    return (
        "温馨提醒💕\n"
        "\n"
        f"你好 这里是{text.clinic_name} 🦷\n"
        f"NAME: {name}\n"
        f"DATE: {day:%d/%m/%y}\n"
        f"TIME: {when}\n"
        f"DOCTOR: {doctor}\n"
        f"BRANCH：{text.branch}\n"
        "想提醒你和我们有个预约 记得赴约哟😊到时见❤️如果有事情耽搁没办法准时到或想取消预约，请通知我们哦😊谢谢你💕\n"
        "\n"
        "Gentle Reminder💕\n"
        "\n"
        f"Hello, we are {text.clinic_name_en} 🦷 Kindly remind you that you have an appointment with us "
        "on the date above 😊\n"
        "If there is any problem, pls contact us😊 Thank you 💕 See you!"
    )


def build_reminder_list(
    dates: list[date],
    appointments: list[ReminderAppointment],
    rules: ClinicRules,
    doctor_names: dict[str, str],
    text: ReminderText = ReminderText(),
    opted_out: frozenset[str] = frozenset(),
) -> ReminderList:
    wanted = set(dates)
    offday_doctors = {
        (a.appointment_date, (a.doctor_id or "").strip().upper())
        for a in appointments
        if a.appointment_date in wanted and "OFFDAY" in normalize_remarks(a.remarks)
    }
    not_appointments: Counter[str] = Counter()
    # key → [(contact_id, line), …]；同一个号码、同一天一组；没有号码的病人各自一组
    groups: dict[tuple, list[tuple[int | None, ReminderLine]]] = {}
    phones: dict[tuple, tuple[str | None, PhoneKind]] = {}
    seen: set[int] = set()

    def order(a: ReminderAppointment):
        return a.appointment_date, parse_slot(a.time_slot) or 0, a.appointment_id

    for a in sorted(appointments, key=order):
        if a.appointment_date not in wanted or a.appointment_id in seen:
            continue
        seen.add(a.appointment_id)
        if (a.status or "").strip().lower() in IGNORED_STATUSES:
            not_appointments["Cancelled or postponed"] += 1
            continue
        if "OFFDAY" in normalize_remarks(a.remarks):
            not_appointments["OFF DAY record"] += 1
            continue
        if (a.time_slot or "").strip() == "00:00":
            not_appointments["To-do at 00:00"] += 1
            continue

        slot = parse_slot(a.time_slot)
        doctor = (a.doctor_id or "").strip().upper()
        phone = normalize_phone(a.hp_no)
        kind = phone_kind(phone)
        key = (a.appointment_date, phone) if kind in SENDABLE or kind == PhoneKind.LANDLINE \
            else (a.appointment_date, "contact", a.contact_id if a.contact_id is not None else -a.appointment_id)
        phones[key] = (phone, kind)

        line = ReminderLine(
            appointment_ids=(a.appointment_id,),
            day=a.appointment_date,
            slot=time(slot // 60, slot % 60) if slot is not None else None,
            doctor_id=doctor,
            patient_name=_clean_name(a.contact_name),
            status=a.status,
            problems=tuple(_problems(a, slot, rules, offday_doctors)),
        )
        members = groups.setdefault(key, [])
        # 同一位病人、同一时段、同一位医生重复的记录 → 合成一行
        for i, (contact_id, old) in enumerate(members):
            if contact_id == a.contact_id and old.slot == line.slot and old.doctor_id == line.doctor_id:
                members[i] = (contact_id, ReminderLine(
                    old.appointment_ids + line.appointment_ids, old.day, old.slot, old.doctor_id,
                    old.patient_name, old.status, tuple(dict.fromkeys(old.problems + line.problems)),
                ))
                break
        else:
            members.append((a.contact_id, line))

    ready: list[ReminderGroup] = []
    needs_staff: list[ReminderGroup] = []
    for key, members in groups.items():
        lines = tuple(line for _, line in members)
        phone, kind = phones[key]
        group_problems: list[str] = []
        if kind == PhoneKind.MISSING:
            group_problems.append("No mobile number in GPiS")
        elif kind == PhoneKind.LANDLINE:
            group_problems.append("Not a mobile number")
        elif phone in opted_out:
            group_problems.append("Opted out of reminders")
        if len(lines) > MAX_LINES_PER_MESSAGE:
            group_problems.append(f"More than {MAX_LINES_PER_MESSAGE} appointments on one number")
        problems = tuple(dict.fromkeys(group_problems + [p for ln in lines for p in ln.problems]))
        group = ReminderGroup(
            day=lines[0].day,
            phone=phone,
            phone_kind=kind,
            lines=lines,
            problems=problems,
            message=render_message(lines, doctor_names, text) if kind in SENDABLE else None,
        )
        # 一位家人有问题，整个号码都交给员工：不要只提醒一部分人（8.3）
        (ready if group.ready else needs_staff).append(group)

    def first(g: ReminderGroup):
        return g.day, g.lines[0].slot or time(0), g.lines[0].patient_name

    return ReminderList(
        dates=tuple(sorted(wanted)),
        ready=tuple(sorted(ready, key=first)),
        needs_staff=tuple(sorted(needs_staff, key=first)),
        not_appointments=tuple(sorted(not_appointments.items())),
    )
