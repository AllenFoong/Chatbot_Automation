"""提醒名单的假资料（REMINDER_SOURCE=demo）：不连 GPiS，也能看 Reminders 页面、试 Open in WhatsApp。

- 全部是假名字（CLAUDE.md 规则 4）。
- 第一位病人的号码 = WHATSAPP_ALLOWED_RECIPIENTS 的第一个号码（自己的手机），
  所以只有这一组会出现 Open in WhatsApp（D54：不是正式资料时，只给允许名单里的号码）。
- 每一天都一样：合成一条的家人、没有 *C、有 *C、固网、没有号码、取消、00:00 各一个。
"""

from __future__ import annotations

from datetime import date, timedelta

from .config import get_whatsapp_settings
from .gpis import GpisPatient, PastVisit, patients_from_rows
from .reminders import ReminderAppointment

FALLBACK_PHONE = "60120000001"


class DemoReminderSource:
    label = "Demo data"
    is_production = False
    fake_data = True        # 全部是假名字：确认消息可以发给允许名单里的号码（app/confirm.py may_send）

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

    # ---------- 找病人（6a-3b，AI 的工具用）：同一批假资料，往前看 30 天 ----------

    def patients_for_phone(self, phone: str) -> list[GpisPatient]:
        today = date.today()
        rows = self.reminder_appointments(today - timedelta(days=30), today)
        return patients_from_rows(((a.contact_id, a.contact_name, a.appointment_date, a.hp_no) for a in rows), phone)

    def visits_of(self, contact_id: int, first: date, last: date) -> list[PastVisit]:
        first = max(first, last - timedelta(days=60))     # 假资料每天都一样，不用看太多天
        return [PastVisit(a.appointment_date, a.doctor_id, a.status, a.remarks)
                for a in self.reminder_appointments(first, last) if a.contact_id == contact_id]

