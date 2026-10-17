"""放一些假资料到开发用的数据库，方便看 Admin Platform 的画面。
Phase 5 接上 WhatsApp 之前，对话和预约请求都是空的。

用法（在 backend/ 里，先执行 seed）：python -m app.db.demo
- 全部是假名字、假号码（CLAUDE.md 规则 4）。
- 只能用在名字以 _dev 结尾的数据库；数据库里已经有对话就不做（不会重复放）。

测 6a-2b 的「确认后自动通知」：python -m app.db.demo --request-for 60123456789 [--date 2026-10-23]
- 给自己手机的那段对话（先用手机传一条消息给 Meta 测试号码）加一个 PENDING 的请求：Demo Self、S+P、PHANG 10:00。
- 日期不填 = 下一个星期五（REMINDER_SOURCE=demo 的假资料每天 10:00 都有 PHANG 的 DEMO PATIENT A）。
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import conversations as conv
from .appointment_requests import cancel_request, create_appointment_request, new_group_id
from .customers import create_customer
from .models import ClinicSettings, Conversation, Customer, Sender
from .session import new_session


def add_demo_data(session: Session, today: date) -> None:
    friday = next_friday(today)
    say = conv.record_outgoing_message

    # 1. 妈妈帮两个孩子约洗牙（同一个号码、两位病人、一起来）→ 2 个 PENDING 请求
    m, _ = conv.record_incoming_message(session, "60120000001", "Hi, can I book scaling for my 2 kids?",
                                        "demo.1", profile_name="Demo Mum")
    say(session, m.conversation, Sender.BOT, f"Sure! Dr PHANG has slots on {friday:%d %b} at 16:00. "
                                             "May I have the children's names?")
    conv.record_incoming_message(session, "60120000001", "Demo Kid A and Demo Kid B. 4pm is ok", "demo.2")
    say(session, m.conversation, Sender.BOT, "Noted. Our staff will confirm shortly.")
    group = new_group_id()
    for name in ("Demo Kid A", "Demo Kid B"):
        kid = create_customer(session, name, "60120000001")
        create_appointment_request(session, kid, "S+P", conversation=m.conversation, doctor_id="PHANG",
                                   preferred_date=friday, preferred_slot=time(16), group_id=group,
                                   notes="Coming together with sibling (WITH)")

    # 2. 矫正每月复诊 → 1 个 PENDING 请求
    m, _ = conv.record_incoming_message(session, "60120000002", "Hello, my monthly OR appointment please",
                                        "demo.3", profile_name="Demo Patient")
    say(session, m.conversation, Sender.BOT, "Your braces doctor is Dr GOH. Is next Saturday morning ok?")
    patient = create_customer(session, "Demo Patient", "60120000002", gpis_contact_id=900001)
    create_appointment_request(session, patient, "OR", conversation=m.conversation, doctor_id="GOH",
                               preferred_date=friday + timedelta(days=1), preferred_slot=time(10))

    # 3. 牙痛要真人 → AI 转人工（HUMAN）
    m, _ = conv.record_incoming_message(session, "6590000003", "My tooth is very painful, can I talk to someone?",
                                        "demo.4", profile_name="Demo SG")
    conv.hand_over_to_human(session, m.conversation, "Patient is in pain and asked for a human")

    # 4. 已经结束的对话：病人取消了请求
    m, _ = conv.record_incoming_message(session, "60120000004", "Sorry, please cancel my check up",
                                        "demo.5", profile_name="Demo Cancel")
    patient = create_customer(session, "Demo Cancel", "60120000004")
    r = create_appointment_request(session, patient, "C/UP", conversation=m.conversation,
                                   preferred_date=friday, preferred_slot=time(9, 30))
    cancel_request(session, r)
    say(session, m.conversation, Sender.BOT, "Your request has been cancelled.")
    conv.close_conversation(session, m.conversation)


def next_friday(today: date) -> date:
    return today + timedelta(days=(4 - today.weekday()) % 7 or 7)


def add_request_for(session: Session, wa_phone: str, day: date) -> int | None:
    """给这个号码现在的对话加一个 PENDING 请求（Demo Self、S+P、PHANG 10:00）。没有对话 = None。"""
    contact = conv.get_or_create_wa_contact(session, wa_phone)
    conversation = conv.get_open_conversation(session, contact.id)
    if conversation is None:
        return None
    customer = session.scalar(select(Customer).where(Customer.name == "Demo Self", Customer.phone == wa_phone))
    if customer is None:
        customer = create_customer(session, "Demo Self", wa_phone)
    request = create_appointment_request(session, customer, "S+P", conversation=conversation, doctor_id="PHANG",
                                         preferred_date=day, preferred_slot=time(10))
    return request.id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.db.demo", description="Add demo data (fake names)")
    parser.add_argument("--request-for", metavar="PHONE", help="add a pending request to this number's conversation")
    parser.add_argument("--date", type=date.fromisoformat, help="date of that request (default: next Friday)")
    args = parser.parse_args(argv)
    with new_session() as session:
        database = session.get_bind().url.database or ""
        if not database.endswith("_dev"):
            print(f"Database {database!r} does not end with _dev: demo data is only for the development database.")
            return 1
        if session.get(ClinicSettings, 1) is None:
            print("Run python -m app.db.seed first.")
            return 1
        if args.request_for:
            from ..phone import normalize_phone

            phone = normalize_phone(args.request_for)
            day = args.date or next_friday(date.today())
            request_id = add_request_for(session, phone, day) if phone else None
            if request_id is None:
                print("No open conversation for that number: send a WhatsApp message to the test number first.")
                return 1
            session.commit()
            print(f"Added pending request {request_id}: Demo Self, S+P, PHANG, {day:%Y-%m-%d} 10:00.")
            return 0
        if session.scalar(select(func.count()).select_from(Conversation)):
            print("There are already conversations: demo data not added.")
            return 0
        add_demo_data(session, date.today())
        session.commit()
    print("Added demo data: 4 conversations, 4 appointment requests (fake names and numbers).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
