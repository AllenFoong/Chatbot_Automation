"""PENDING 的请求和 GPiS 的预约对不对得上（D70，docs/architecture.md 11.6）。

这里只做计算，不连接数据库：输入是请求和 GPiS 那一天、那几位病人的预约（gpis.py 读出），
输出是哪一个请求对上哪一个预约。读、改数据库、发消息在 app/request_matcher.py。

对上 = 同一位病人（ContactID）、同一天、同一个时段、同一位医生，而且这个预约算病人（不是 Canceled / Postpone、
不是 OFF DAY）。一个请求只能对一个预约、一个预约只能对一个请求：对得上两个的都不自动，留给员工。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, time

from .availability import IGNORED_STATUSES, GpisAppointment, parse_appointment, parse_slot
from .reminders import ReminderText, _clean_name, _time_12h


@dataclass(frozen=True)
class BookedAppointment:
    """从 GPiS 读出的一个病人的预约（找请求用的栏位；没有名字、号码）。"""

    appointment_id: int
    appointment_date: date
    time_slot: str | None
    doctor_id: str | None
    status: str | None
    contact_id: int | None
    remarks: str | None


@dataclass(frozen=True)
class RequestToMatch:
    """一个 PENDING 的请求（只有对得上要用的栏位）。"""

    request_id: int
    contact_id: int          # 病人的 GPiS ContactID；新病人没有 → 不找，由员工按
    day: date
    slot: time
    doctor_id: str


def counts_as_booking(a: BookedAppointment, clinic_contact_id: int) -> bool:
    """算不算一个病人的预约（和查空档的判断一样）。"""
    if (a.status or "").strip().lower() in IGNORED_STATUSES:
        return False
    parsed = parse_appointment(
        GpisAppointment(a.appointment_id, a.time_slot, a.status, a.contact_id, a.remarks), clinic_contact_id
    )
    return parsed.occupies


def same_booking(r: RequestToMatch, a: BookedAppointment) -> bool:
    return (
        a.contact_id == r.contact_id
        and a.appointment_date == r.day
        and parse_slot(a.time_slot) == r.slot.hour * 60 + r.slot.minute
        and (a.doctor_id or "").strip().upper() == r.doctor_id.strip().upper()
    )


def find_matches(
    requests: list[RequestToMatch],
    appointments: list[BookedAppointment],
    clinic_contact_id: int,
    already_linked: set[int] | frozenset[int] = frozenset(),
) -> dict[int, int]:
    """{request_id: appointment_id}，只有一对一的。

    already_linked：已经记在别的请求上的 GPiS 预约（例：改期时 AppointmentID 不变，W5），不再拿来对。
    """
    usable = [
        a for a in appointments
        if a.appointment_id not in already_linked and counts_as_booking(a, clinic_contact_id)
    ]
    candidates = {r.request_id: {a.appointment_id for a in usable if same_booking(r, a)} for r in requests}
    per_appointment = Counter(aid for ids in candidates.values() for aid in ids)
    return {
        rid: next(iter(ids))
        for rid, ids in candidates.items()
        if len(ids) == 1 and per_appointment[next(iter(ids))] == 1
    }


def render_confirmation(patient_name: str, day: date, slot: time, doctor_name: str, text: ReminderText) -> str:
    """确认消息（草稿：W61、W68 回答之后再改）。日期、时间、医生 = GPiS 的（对上了才发）。"""
    return (
        "预约已确认 ✅\n"
        "\n"
        f"你好 这里是{text.clinic_name} 🦷\n"
        f"NAME: {_clean_name(patient_name)}\n"
        f"DATE: {day:%d/%m/%y} ({day:%a})\n"
        f"TIME: {_time_12h(slot)}\n"
        f"DOCTOR: DR {doctor_name.upper()}\n"
        f"BRANCH：{text.branch}\n"
        "如果有事情耽搁没办法准时到或想改期、取消，请通知我们哦😊谢谢你💕\n"
        "\n"
        "Appointment confirmed ✅\n"
        "\n"
        f"Hello, we are {text.clinic_name_en} 🦷 Your appointment is confirmed for the date above 😊\n"
        "If you need to change or cancel it, pls contact us😊 Thank you 💕 See you!"
    )
