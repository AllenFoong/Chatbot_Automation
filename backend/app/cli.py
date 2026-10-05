"""在终端印出某天的空档，格式和 SQL 的 7a / 7b / 7c 一样，方便对照。

用法（在 backend/ 里）：python -m app.cli 2026-09-02 PHANG S+P
预约读 GPiS（GPIS_CONNECTION_STRING），诊所设置读本系统的 PostgreSQL（DATABASE_URL）。
输出不含病人名字和 Remarks。
"""

from __future__ import annotations

import sys
from datetime import date

from .availability import check_available_slots
from .db.rules import load_clinic_rules
from .db.session import new_session
from .main import _default_reader


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    day, doctor, service = date.fromisoformat(argv[0]), argv[1], argv[2]
    with new_session() as session:
        rules = load_clinic_rules(session)
    r = check_available_slots(day, doctor, service, _default_reader().appointments_for(day, doctor), rules)

    print(f"7a  {r.date} {r.weekday}  {r.doctor}  {r.service}  {r.day_status}  Patients={r.patients}")
    if r.note:
        print(f"    {r.note}")
    print("\n7b  Slot   Kind         Booked  Cap  Remaining  Can30  Can60")
    for s in r.slots:
        cap = "" if s.cap is None else s.cap
        print(f"    {s.time}  {s.kind:<11}  {s.booked:>6}  {cap!s:>3}  {s.remaining:>9}  {int(s.can_30):>5}  {int(s.can_60):>5}")
    print("\n7c  AppointmentID  TimeSlot  Status      DurSlots  Placeholder  OffDay  HourUnparsed  Occupies")
    for a in r.appointments:
        print(f"    {a.appointment_id:>13}  {a.time_slot or '':<8}  {a.status or '':<10}  {a.dur_slots:>8}  "
              f"{int(a.is_placeholder):>11}  {int(a.is_off_day):>6}  {int(a.hour_unparsed):>12}  {int(a.occupies):>8}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
