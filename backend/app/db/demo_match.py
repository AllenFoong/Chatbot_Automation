"""开发电脑试「每 3 分钟找 GPiS 的预约」（D70）用的假请求。

用法（在 backend/ 里，.env 要有 REMINDER_SOURCE=demo）：
  python -m app.db.demo_match            明天放 2 个 PENDING 请求
  python -m app.db.demo_match --remove   删掉这些假请求和假病人

- 请求 A：明天 10:00、Demo Patient A 的 ContactID（9001）→ 和假的预约来源（app/reminder_demo.py）一样 → 会自动确认
- 请求 B：明天 11:30、ContactID 9003 → 假资料里是 11:00（员工约成别的时间）→ 不会自动确认，一直算占用
- 病人的号码 = WHATSAPP_ALLOWED_RECIPIENTS 的第一个（自己的手机）。这个号码有没结束的对话，请求就接在那段对话上
  （24 小时内传过消息，系统会发确认）；没有就不接（系统不发，标「要通知」）。
- 只能用在名字以 _dev 结尾的数据库，而且只能配假的预约来源：GPiS_Dev 里可能真的有 ContactID 9001 的病人。
"""

from __future__ import annotations

import sys
from datetime import time, timedelta

from sqlalchemy import delete, select

from ..config import get_whatsapp_settings, reminder_source_name
from ..reminder_demo import DemoReminderSource
from ..reminders import clinic_today
from . import conversations as conv
from .appointment_requests import create_appointment_request
from .models import AppointmentRequest, ClinicSettings, Customer, WaContact
from .session import new_session

NAME_PREFIX = "Demo Match"


def main(argv: list[str]) -> int:
    if argv not in ([], ["--remove"]):
        print(__doc__)
        return 2
    if reminder_source_name() != "demo":
        print("Set REMINDER_SOURCE=demo in backend/.env first (fake appointments only).")
        return 1
    with new_session() as session:
        database = session.get_bind().url.database or ""
        if not database.endswith("_dev"):
            print(f"Database {database!r} does not end with _dev: demo data is only for the development database.")
            return 1
        customers = select(Customer.id).where(Customer.name.startswith(NAME_PREFIX))
        if argv == ["--remove"]:
            n = session.execute(delete(AppointmentRequest).where(AppointmentRequest.customer_id.in_(customers)))
            session.execute(delete(Customer).where(Customer.name.startswith(NAME_PREFIX)))
            session.commit()
            print(f"Removed {n.rowcount} demo match requests.")
            return 0
        if session.get(ClinicSettings, 1) is None:
            print("Run python -m app.db.seed first.")
            return 1
        if session.scalar(customers.limit(1)) is not None:
            print("Demo match requests are already there: run with --remove first.")
            return 1

        phone = DemoReminderSource.from_settings().own_phone
        contact = session.scalars(select(WaContact).where(WaContact.wa_phone == phone)).one_or_none()
        conversation = conv.get_open_conversation(session, contact.id) if contact else None
        day = clinic_today() + timedelta(days=1)
        doctor = "GOH" if day.isoweekday() == 2 else "PHANG"     # 和 reminder_demo.py 的 doc1 一样
        made = []
        for contact_id, letter, slot in ((9001, "A", time(10, 0)), (9003, "C", time(11, 30))):
            patient = Customer(name=f"{NAME_PREFIX} {letter}", phone=phone, gpis_contact_id=contact_id)
            session.add(patient)
            session.flush()
            made.append(create_appointment_request(session, patient, "S+P", conversation=conversation,
                                                   doctor_id=doctor, preferred_date=day, preferred_slot=slot))
        session.commit()
        allowed = get_whatsapp_settings().allowed_recipients
        print(f"Added 2 PENDING requests for {day:%Y-%m-%d} with {doctor}: "
              f"#{made[0].id} at 10:00 (will match), #{made[1].id} at 11:30 (will not match).")
        print("Linked to the open WhatsApp conversation of your own number." if conversation else
              "Your own number has no open conversation: the system will not send, it will ask staff to tell.")
        if not allowed:
            print("Note: WHATSAPP_ALLOWED_RECIPIENTS is empty, so a fake number is used.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
