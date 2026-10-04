"""诊所的设置：排班、午休、每格上限、能当第 3 人的疗程、休息日、请假。

和 sql/check_available_slots.sql 第 2 节一样。将来会搬到本系统的 PostgreSQL
（doctor_schedules、services、clinic_closures、settings），由员工在 Admin Platform 修改。
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
    closures: dict[date, str] = field(default_factory=dict)
    doctor_leaves: frozenset[tuple[str, date]] = frozenset()
    max_per_slot: int = 3            # W22
    max_per_slot_for_ai: int = 3     # 改成 2 = AI 不用第 3 个名额
    clinic_contact_id: int = 34094   # 诊所自己当联系人（统计 B6）


def _t(hhmm: str) -> time:
    return time.fromisoformat(hhmm)


_PHANG_DAY = DaySchedule(_t("09:00"), _t("16:30"), _t("12:00"), _t("13:00"))
_GOH_DAY = DaySchedule(_t("09:00"), _t("15:30"), _t("13:00"), _t("14:00"))
_GOH_TUESDAY = DaySchedule(_t("09:00"), _t("15:30"), _t("12:00"), _t("13:00"))

DEFAULT_RULES = ClinicRules(
    schedules={
        "PHANG": {
            1: _PHANG_DAY,
            2: None,            # 星期二休息
            3: _PHANG_DAY,
            4: _PHANG_DAY,
            5: _PHANG_DAY,
            6: _PHANG_DAY,
            7: _PHANG_DAY,
        },
        "GOH": {
            1: _GOH_DAY,
            2: _GOH_TUESDAY,    # 星期二午休 12:00
            3: None,            # 星期三休息
            4: None,            # 星期四休息
            5: _GOH_DAY,
            6: _GOH_DAY,
            7: _GOH_DAY,
        },
    },
    can_be_third=frozenset({"OR", "S+P", "F", "RETAINER"}),  # W15
    # 全国 + Johor 公共假期、农历新年多休的日子（W1、W14），例：{date(2026, 12, 25): "Christmas"}
    closures={},
    # 本系统记录的医生请假（备用；GPiS 里的 OFF DAY 也会检查，W25），例：{("GOH", date(2026, 10, 10))}
    doctor_leaves=frozenset(),
)
