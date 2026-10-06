"""第一次建数据库时写入的诊所设置（= Phase 1 SQL 第 2 节、Phase 2 的 clinic_rules.py）。

用法（在 backend/ 里，先执行 alembic upgrade head）：python -m app.db.seed
只补上数据库里还没有的设置，不会覆盖员工改过的值，所以重复执行也没关系。
规则来源：docs/clinic-workflow.md 第 1、2、6 节；D15、D16。
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import time

from sqlalchemy.orm import Session

from .models import ClinicSettings, Doctor, DoctorSchedule, Service
from .session import new_session

# (DoctorID, 显示的名字, Remarks 里的标记)
DOCTORS = [
    ("PHANG", "PHANG", "P"),
    ("GOH", "GOH", "G"),
]

# 排班（W13、W20、W21）：(开始, 最后一格, 午休开始, 午休结束)；None = 这天休息
_PHANG = ("09:00", "16:30", "12:00", "13:00")
_GOH = ("09:00", "15:30", "13:00", "14:00")
_GOH_TUESDAY = ("09:00", "15:30", "12:00", "13:00")     # 星期二午休 12:00

SCHEDULES = {
    #         一      二            三      四      五      六      日
    "PHANG": [_PHANG, None,         _PHANG, _PHANG, _PHANG, _PHANG, _PHANG],
    "GOH":   [_GOH,   _GOH_TUESDAY, None,   None,   _GOH,   _GOH,   _GOH],
}

# (代码, 名字, 能当第 3 人, 可能要 1 hour, AI 能自己推荐时段, 多步骤疗程类别)
# 能当第 3 人：W15。可能要 1 hour：W16（诊所举的例子，不一定完整）；ISSUE BRIDGE 不用（W30）。
# AI 能推荐：S+P、F、C/UP 和矫正的后续预约（OR、RB、RETAINER）；其他收集需求后转员工（D15、D16、D33）。
# 牙冠、牙桥分两次（扫描 → 戴上），要同一位医生（W29、D33）。
SERVICES = [
    ("C/UP", "Check up", False, False, True, None),
    ("F", "Filling", True, False, True, None),
    ("S+P", "Scaling & polishing", True, False, True, None),
    ("XLA", "Extraction", False, False, False, None),
    ("MOS", "Minor oral surgery (wisdom tooth)", False, False, False, None),
    ("WHITENING", "Whitening", False, False, False, None),
    ("VENEER", "Veneer", False, True, False, None),
    ("INVISALIGN", "Invisalign", False, False, False, None),
    ("SC", "Scan crown", False, False, False, "CROWN"),
    ("ISSUE CROWN", "Issue crown", False, False, False, "CROWN"),
    ("SCAN B", "Scan bridge", False, True, False, "BRIDGE"),
    ("ISSUE BRIDGE", "Issue bridge", False, False, False, "BRIDGE"),
    ("RCT", "Root canal treatment", False, True, False, "RCT"),
    ("IMPLANT", "Implant", False, True, False, "IMPLANT"),
    ("STO", "Suture take out", False, False, False, "IMPLANT"),
    ("PUT HA", "Put abutment", False, False, False, "IMPLANT"),
    ("IMP IMPLANT", "Implant impression", False, False, False, "IMPLANT"),
    ("ISSUE IMPLANT", "Issue implant", False, False, False, "IMPLANT"),
    ("DENTURE", "Denture", False, False, False, "DENTURE"),
    ("MMR", "Bite registration", False, False, False, "DENTURE"),
    ("TRY-IN", "Denture try-in", False, False, False, "DENTURE"),
    ("ISSUE DENTURE", "Issue denture", False, False, False, "DENTURE"),
    ("ON", "Braces on", False, False, False, "ORTHO"),
    ("OR", "Ortho monthly review", True, False, True, "ORTHO"),
    ("RB", "Rebond bracket", False, False, True, "ORTHO"),
    ("RETAINER", "Retainer", True, False, True, "ORTHO"),
]

SETTINGS = {
    "max_per_slot": 3,              # W22
    "max_per_slot_for_ai": 3,
    "clinic_contact_id": 34094,     # 诊所自己当联系人（统计 B6）
}


def seed(session: Session) -> Counter[str]:
    """补上还没有的设置，回传每张表新增了几行。不会 commit（由调用的人决定）。"""
    added: Counter[str] = Counter()

    def add_if_missing(model, key, **values) -> None:
        if session.get(model, key) is None:
            session.add(model(**values))
            added[model.__tablename__] += 1

    for doctor_id, display_name, tag in DOCTORS:
        add_if_missing(Doctor, doctor_id, id=doctor_id, display_name=display_name, remark_tag=tag)
    session.flush()     # 先有医生，才能加排班

    for doctor_id, week in SCHEDULES.items():
        for weekday, day in enumerate(week, start=1):
            hours = {}
            if day is not None:
                hours = dict(zip(("start_time", "last_slot", "break_start", "break_end"), map(time.fromisoformat, day)))
            add_if_missing(DoctorSchedule, (doctor_id, weekday),
                           doctor_id=doctor_id, weekday=weekday, is_working=day is not None, **hours)

    for code, name, third, one_hour, ai, group in SERVICES:
        add_if_missing(Service, code, code=code, name=name, can_be_third=third,
                       may_need_1h=one_hour, ai_can_book=ai, treatment_group=group)

    add_if_missing(ClinicSettings, 1, id=1, **SETTINGS)
    session.flush()
    return added


def main() -> int:
    with new_session() as session:
        added = seed(session)
        session.commit()
    if not added:
        print("设置都已经在数据库里，没有新增。")
    for table, n in sorted(added.items()):
        print(f"{table}: 新增 {n} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
