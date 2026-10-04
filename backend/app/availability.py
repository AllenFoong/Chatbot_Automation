"""空档计算：sql/check_available_slots.sql 的 Python 版本。

这里只做计算，不连接数据库：输入是 GPiS 当天的预约（由 gpis.py 读出），
输出是每个时段还能不能约。Remarks 只在内存里用来判断时长、OFF DAY，不会出现在输出里。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time

from .clinic_rules import ClinicRules

SLOT_MINUTES = 30
# 和 SQL 一样只认这两个状态为"不占位"（SQL Server 比较不分大小写）
IGNORED_STATUSES = {"canceled", "postpone"}
_SLOT_PATTERN = re.compile(r"[0-2][0-9]:[0-5][0-9]")
_DIGIT_HR = re.compile(r"[0-9]HR")

# 时长写法（W17、W23、W24）：先判断长的，再判断短的；xxMIN 一律当 1 格
_DUR_4 = ("2HOUR", "2HR")
_DUR_3 = ("1.5HOUR", "1.5HR", "1.5H)", "1.30HOUR", "1HOUR30", "1HOURS30", "1HR30")
_DUR_2 = ("1HOUR", "1HR", "(1H)")


@dataclass(frozen=True)
class GpisAppointment:
    """从 Tbl_CAH_Appointment 读出的一条预约（只取计算需要的栏位）。"""

    appointment_id: int
    time_slot: str | None
    status: str | None
    contact_id: int | None
    remarks: str | None


@dataclass(frozen=True)
class ParsedAppointment:
    """一条预约怎么被解读（对应 SQL 输出 7c）。没有名字和 Remarks。"""

    appointment_id: int
    time_slot: str | None
    slot: int | None          # 从午夜开始的分钟数；00:00（提醒）和格式不对 = None，不占时段
    status: str | None
    is_placeholder: bool
    is_off_day: bool
    dur_slots: int
    hour_unparsed: bool

    @property
    def occupies(self) -> bool:
        """算不算病人：有时段，而且不是诊所占位、不是 OFF DAY。"""
        return self.slot is not None and not self.is_placeholder and not self.is_off_day


@dataclass(frozen=True)
class SlotResult:
    """一个时段（对应 SQL 输出 7b）。"""

    time: str
    kind: str                 # "" / "BREAK" / "LONG APPT" / "AFTER HOURS"
    booked: int
    cap: int | None
    remaining: int
    can_30: bool
    can_60: bool


@dataclass(frozen=True)
class DayAvailability:
    """一天的结果（对应 SQL 输出 7a + 7b + 7c）。"""

    date: date
    weekday: str
    doctor: str
    service: str
    day_status: str
    note: str | None
    patients: int
    slots: list[SlotResult]
    appointments: list[ParsedAppointment]

    @property
    def bookable(self) -> bool:
        """AI 能不能自动推荐这天的空档（NEEDS_REVIEW 照算，但要转员工）。"""
        return self.day_status == "OK"


def normalize_remarks(remarks: str | None) -> str:
    """Remarks 转大写、去掉空格、Tab 和 *（和 SQL 的 R 一样）。"""
    return (remarks or "").replace(" ", "").replace("\t", "").replace("*", "").upper()


def duration_slots(r: str) -> int:
    if any(p in r for p in _DUR_4):
        return 4
    if any(p in r for p in _DUR_3):
        return 3
    if any(p in r for p in _DUR_2):
        return 2
    return 1


def parse_slot(time_slot: str | None) -> int | None:
    """"HH:MM" → 分钟数；00:00 和格式不对的 → None。"""
    s = (time_slot or "").strip()
    if not _SLOT_PATTERN.fullmatch(s) or s == "00:00":
        return None
    hours, minutes = int(s[:2]), int(s[3:])
    if hours > 23:
        return None
    return hours * 60 + minutes


def parse_appointment(a: GpisAppointment, clinic_contact_id: int) -> ParsedAppointment:
    r = normalize_remarks(a.remarks)
    dur = duration_slots(r)
    return ParsedAppointment(
        appointment_id=a.appointment_id,
        time_slot=a.time_slot,
        slot=parse_slot(a.time_slot),
        status=a.status,
        is_placeholder=a.contact_id == clinic_contact_id,
        # OFF DAY：任何联系人、任何时段（包括 00:00），去掉空格后含 OFFDAY（C5）
        is_off_day="OFFDAY" in r,
        dur_slots=dur,
        # 有 HOUR / HR 字样但看不懂 → 当天转人工
        hour_unparsed=dur == 1 and ("HOUR" in r or _DIGIT_HR.search(r) is not None),
    )


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def check_available_slots(
    day: date,
    doctor_id: str,
    service: str,
    gpis_appointments: list[GpisAppointment],
    rules: ClinicRules,
) -> DayAvailability:
    doctor_id = doctor_id.strip().upper()
    service = service.strip().upper()

    appts = [
        parse_appointment(a, rules.clinic_contact_id)
        for a in gpis_appointments
        if (a.status or "").strip().lower() not in IGNORED_STATUSES
    ]

    # ---------- 这位医生这天的排班 ----------
    week = rules.schedules.get(doctor_id)
    schedule = week.get(day.isoweekday()) if week else None

    # ---------- 这天的状态（优先次序和 SQL 第 5 节一样） ----------
    if week is None:
        day_status, note = "UNKNOWN_DOCTOR", "排班表里没有这位医生"
    elif day in rules.closures:
        day_status, note = "CLINIC_CLOSED", rules.closures[day]
    elif schedule is None:
        day_status, note = "DOCTOR_NOT_WORKING", "这位医生这天固定休息"
    elif (doctor_id, day) in rules.doctor_leaves:
        day_status, note = "DOCTOR_ON_LEAVE", "本系统记录了请假"
    elif any(a.is_off_day for a in appts):
        day_status, note = "OFFDAY_IN_GPIS", "GPiS 有 OFF DAY 记录"
    elif any(a.is_placeholder for a in appts):
        day_status, note = "NEEDS_REVIEW", "有诊所联系人的记录（可能是医生的私人安排），AI 不自动推荐"
    elif any(a.hour_unparsed and a.slot is not None for a in appts):
        day_status, note = "NEEDS_REVIEW", "有看不懂的时长写法，AI 不自动推荐"
    else:
        day_status, note = "OK", None

    occupying = [a for a in appts if a.occupies]

    # ---------- 时段表：营业时段 + 最后一格之后的一格（给 1 hour 从最后一格开始用） ----------
    grid: list[tuple[int, bool, bool, int, bool]] = []  # (slot, is_break, after_hours, booked, long_blocked)
    if schedule is not None:
        start, last = _minutes(schedule.start), _minutes(schedule.last_slot)
        b_start = _minutes(schedule.break_start) if schedule.break_start else None
        b_end = _minutes(schedule.break_end) if schedule.break_end else None
        for s in range(start, last + SLOT_MINUTES + 1, SLOT_MINUTES):
            is_break = b_start is not None and b_end is not None and b_start <= s < b_end
            booked = sum(1 for a in occupying if a.slot == s)
            long_blocked = any(
                a.dur_slots >= 2 and a.slot <= s < a.slot + SLOT_MINUTES * a.dur_slots
                for a in occupying
            )
            grid.append((s, is_break, s > last, booked, long_blocked))

    can_count = day_status in ("OK", "NEEDS_REVIEW")
    can_be_third = service in rules.can_be_third

    slots: list[SlotResult] = []
    for i, (s, is_break, after_hours, booked, long_blocked) in enumerate(grid):
        prev_booked = grid[i - 1][3] if i > 0 else 0
        has_next = i + 1 < len(grid)
        next_booked = grid[i + 1][3] if has_next else 0
        next_blocked = grid[i + 1][4] if has_next else False
        next_is_break = grid[i + 1][1] if has_next else True

        # 上限：能当第 3 人的疗程，且前后两格都不是 3 人 → 3；否则 2（W2、W15、W22）
        cap_rule = 3 if can_be_third and prev_booked < 3 and next_booked < 3 else 2
        cap = min(cap_rule, rules.max_per_slot, rules.max_per_slot_for_ai)

        closed = is_break or after_hours or long_blocked
        open_slot = can_count and not closed

        if after_hours:
            kind = "AFTER HOURS"
        elif is_break:
            kind = "BREAK"
        elif long_blocked:
            kind = "LONG APPT"
        else:
            kind = ""

        slots.append(
            SlotResult(
                time=_hhmm(s),
                kind=kind,
                booked=booked,
                cap=None if closed else cap,
                remaining=max(cap - booked, 0) if open_slot else 0,
                can_30=open_slot and booked < cap,
                # 1 hour：这格和下一格都空、都没封锁、下一格不是午休
                # （最后一格的下一格是 AFTER HOURS，可以用，W16、W27）
                can_60=open_slot and booked == 0 and next_booked == 0
                and not next_blocked and not next_is_break,
            )
        )

    return DayAvailability(
        date=day,
        weekday=day.strftime("%A"),
        doctor=doctor_id,
        service=service,
        day_status=day_status,
        note=note,
        patients=len(occupying),
        slots=slots,
        appointments=sorted(appts, key=lambda a: ((a.time_slot or ""), a.appointment_id)),
    )
