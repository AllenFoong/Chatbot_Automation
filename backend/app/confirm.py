"""员工按 Entered in GPiS ✓：当场查 GPiS、点选是哪一个预约、确认消息（Phase 6a-2b，D71 ①）。

这里只做计算，不连接数据库：输入是 GPiS 那一天的预约（gpis.py / 假资料读出，和提醒用同一个来源），
输出是给员工点选的名单和确认消息。

- 名单只有算病人的预约（和空档、提醒一样，D41）：取消、OFF DAY、00:00、诊所联系人的都不列。
- 只给时间、名字、医生、ContactID，**不给 Remarks**（疗程是健康资料，D41、D44）。
- 和请求一样的（同 ContactID、同医生、同时段）排在最上面，员工还是要自己点选。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from .availability import IGNORED_STATUSES, normalize_remarks, parse_slot
from .reminders import ReminderAppointment, ReminderSource, ReminderText, _clean_name, _time_12h


@dataclass(frozen=True)
class GpisChoice:
    """GPiS 里的一个预约，给员工点选。"""

    appointment_id: int
    day: date
    slot: time
    doctor_id: str
    patient_name: str
    contact_id: int | None


@dataclass(frozen=True)
class RequestFacts:
    """拿来排顺序的请求资料。"""

    contact_id: int | None
    doctor_id: str | None
    slot: time | None


def gpis_choices(appointments: list[ReminderAppointment], clinic_contact_id: int) -> list[GpisChoice]:
    choices: list[GpisChoice] = []
    seen: set[int] = set()
    for a in appointments:
        minutes = parse_slot(a.time_slot)
        if (
            a.appointment_id in seen
            or minutes is None
            or (a.status or "").strip().lower() in IGNORED_STATUSES
            or a.contact_id == clinic_contact_id
            or "OFFDAY" in normalize_remarks(a.remarks)
        ):
            continue
        seen.add(a.appointment_id)
        choices.append(
            GpisChoice(
                appointment_id=a.appointment_id,
                day=a.appointment_date,
                slot=time(minutes // 60, minutes % 60),
                doctor_id=(a.doctor_id or "").strip().upper(),
                patient_name=_clean_name(a.contact_name),
                contact_id=a.contact_id,
            )
        )
    return choices


def match_score(c: GpisChoice, r: RequestFacts) -> int:
    """越像请求分数越高：同一位病人最重要，再来是医生、时段。"""
    return (
        4 * (r.contact_id is not None and c.contact_id == r.contact_id)
        + 2 * (r.doctor_id is not None and c.doctor_id == r.doctor_id.upper())
        + (r.slot is not None and c.slot == r.slot)
    )


def rank(choices: list[GpisChoice], r: RequestFacts) -> list[GpisChoice]:
    return sorted(choices, key=lambda c: (-match_score(c, r), c.slot, c.doctor_id, c.appointment_id))


def may_send(source: ReminderSource) -> bool:
    """确认消息能不能经 WhatsApp 发出、能不能给 Open in WhatsApp（D44、D54 的锁）。

    读主机的 GPiS（正式资料）或假资料才可以；读 GPiS_Dev 的名字是真的病人，不能发到 WhatsApp（规则 4）。
    """
    return source.is_production or bool(getattr(source, "fake_data", False))


def render_confirmation(choice: GpisChoice, doctor_name: str, text: ReminderText) -> str:
    """确认消息（开发者 2026-10-17 定的写法，中英两句）：照 GPiS 的名字、日期、时间、医生（不是病人原来要的）。

    在病人刚传过消息的对话里回（24 小时内），所以不再自我介绍；预约资料照提醒的写法（W32）。
    """
    return (
        "好的哟，已经帮你预约了哦😊\n"
        "Okay, your appointment is booked 😊\n"
        "\n"
        f"NAME: {choice.patient_name}\n"
        f"DATE: {choice.day:%d/%m/%y}\n"
        f"TIME: {_time_12h(choice.slot)}\n"
        f"DOCTOR: DR {doctor_name.upper()}\n"
        f"BRANCH：{text.branch}"
    )
