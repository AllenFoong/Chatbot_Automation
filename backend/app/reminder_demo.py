"""提醒名单的假资料（REMINDER_SOURCE=demo）：不连 GPiS，也能看 Reminders 页面、试 Open in WhatsApp。

- 全部是假名字（CLAUDE.md 规则 4）。
- 第一位病人的号码 = WHATSAPP_ALLOWED_RECIPIENTS 的第一个号码（自己的手机），
  所以只有这一组会出现 Open in WhatsApp（D54：不是正式资料时，只给允许名单里的号码）。
- 每一天都一样：合成一条的家人、没有 *C、有 *C、固网、没有号码、取消、00:00 各一个。
- 每 3 分钟找请求的预约（D70）也可以用这些假资料：ContactID 是 9001–9008（DEMO_CONTACT_IDS）。
"""

from __future__ import annotations

from datetime import date, timedelta

from .config import get_whatsapp_settings
from .matching import BookedAppointment
from .reminders import ReminderAppointment

FALLBACK_PHONE = "60120000001"
DEMO_CONTACT_IDS = range(9001, 9009)


class DemoReminderSource:
    label = "Demo data"
    is_production = False

    def __init__(self, own_phone: str | None = None):
        self.own_phone = own_phone or FALLBACK_PHONE

    @classmethod
    def from_settings(cls) -> DemoReminderSource:
        allowed = get_whatsapp_settings().allowed_recipients
        return cls(sorted(allowed)[0] if allowed else None)

    def reminder_appointments(self, first: date, last: date) -> list[ReminderAppointment]:
        rows: list[ReminderAppointment] = []
        d = first
        while d <= last:
            rows.extend(self._day(d))
            d += timedelta(days=1)
        return rows

    def patient_appointments(self, day: date, contact_ids: set[int]) -> list[BookedAppointment]:
        return [
            BookedAppointment(a.appointment_id, a.appointment_date, a.time_slot, a.doctor_id, a.status,
                              a.contact_id, a.remarks)
            for a in self._day(day)
            if a.contact_id in contact_ids
        ]

    def _day(self, d: date) -> list[ReminderAppointment]:
        weekday = d.isoweekday()
        doc1 = "GOH" if weekday == 2 else "PHANG"           # PHANG 星期二休息
        doc2 = "PHANG" if weekday in (3, 4) else "GOH"      # GOH 星期三、四休息
        base = d.toordinal() * 100
        rows = [
            # (时段, 医生, 状态, 名字, 号码, Remarks)
            ("10:00", doc1, "Confirmed", "Demo Patient A", self.own_phone, "S+P (P) WITH"),
            ("10:30", doc2, "Confirmed", "Demo Patient B", self.own_phone, "OR (G) WITH"),
            ("11:00", doc1, "Confirmed", "Demo Patient C", "012-000 0003", "ISSUE CROWN 36 (P)"),
            ("14:00", doc1, "Confirmed", "Demo Patient D", "012-000 0004", "ISSUE CROWN 46 (P) *C"),
            ("14:30", doc1, "Confirmed", "Demo Patient E", "07-000 0005", "C/UP (P)"),
            ("15:00", doc1, "Confirmed", "Demo Patient F", None, "F (P)"),
            ("15:30", doc1, "Canceled", "Demo Patient G", "012-000 0007", "XLA (P)"),
            ("00:00", doc1, "Confirmed", "Demo Patient H", "012-000 0008", "REMIND PT STO"),
        ]
        return [
            ReminderAppointment(
                appointment_id=base + i,
                appointment_date=d,
                time_slot=slot,
                doctor_id=doctor,
                status=status,
                contact_id=9000 + i,
                contact_name=name,
                hp_no=phone,
                remarks=remarks,
            )
            for i, (slot, doctor, status, name, phone, remarks) in enumerate(rows, start=1)
        ]
