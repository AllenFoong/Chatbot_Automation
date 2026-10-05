"""测试用的诊所设置：和 Phase 1 SQL 第 2 节、Phase 2 的 clinic_rules.py 完全一样（2026-10 的排班）。

- test_availability.py 用它重现 sql/README.md 的测试。
- test_db_rules.py 检查数据库的初始设置（app/db/seed.py）读出来和它一模一样，
  所以设置搬进 PostgreSQL 之后，空档结果和 Phase 2 一样。
"""

from datetime import time

from app.clinic_rules import ClinicRules, DaySchedule

_PHANG_DAY = DaySchedule(time(9, 0), time(16, 30), time(12, 0), time(13, 0))
_GOH_DAY = DaySchedule(time(9, 0), time(15, 30), time(13, 0), time(14, 0))
_GOH_TUESDAY = DaySchedule(time(9, 0), time(15, 30), time(12, 0), time(13, 0))

RULES = ClinicRules(
    schedules={
        "PHANG": {1: _PHANG_DAY, 2: None, 3: _PHANG_DAY, 4: _PHANG_DAY, 5: _PHANG_DAY, 6: _PHANG_DAY, 7: _PHANG_DAY},
        "GOH": {1: _GOH_DAY, 2: _GOH_TUESDAY, 3: None, 4: None, 5: _GOH_DAY, 6: _GOH_DAY, 7: _GOH_DAY},
    },
    can_be_third=frozenset({"OR", "S+P", "F", "RETAINER"}),
    max_per_slot=3,
    max_per_slot_for_ai=3,
    clinic_contact_id=34094,
)
