"""诊所设置在程序里的样子（availability.py 用）：排班、午休、每格上限、能当第 3 人的疗程、休息日、请假。

真正的设置存在本系统的 PostgreSQL（app/db/models.py：doctor_schedules、services、clinic_closures、
doctor_leaves、clinic_settings），由 app/db/rules.py 读出来变成 ClinicRules；初始值在 app/db/seed.py。
改设置要改数据库（Phase 4 在 Admin Platform 改），不是改这里。
规则来源：docs/clinic-workflow.md 第 1、2 节（W13、W15、W20、W21、W22）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time


@dataclass(frozen=True)
class DaySchedule:
    """某医生某个星期几的上班时间。break_start … break_end 之间的格不能约。"""

    start: time
    last_slot: time
    break_start: time | None = None
    break_end: time | None = None


# 星期几：1 = 星期一 … 7 = 星期日（和 date.isoweekday()、SQL 的 SET DATEFIRST 1 一样）
# None = 这天固定休息
WeekSchedule = dict[int, DaySchedule | None]


@dataclass(frozen=True)
class ClinicRules:
    schedules: dict[str, WeekSchedule]
    can_be_third: frozenset[str]
    max_per_slot: int                # 每格最多几人（W22）
    max_per_slot_for_ai: int         # 改成 2 = AI 不用第 3 个名额
    clinic_contact_id: int           # GPiS 里诊所自己当联系人的 ContactID（统计 B6）
    closures: dict[date, str] = field(default_factory=dict)
    doctor_leaves: frozenset[tuple[str, date]] = frozenset()
