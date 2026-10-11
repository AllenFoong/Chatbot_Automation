"""在终端印出提醒名单的摘要，方便和 GPiS 对照、贴给 AI 看（Phase 5b）。

用法（在 backend/ 里）：
    python -m app.reminders_cli                 今天要提醒的日期（明天；假期前连后天）
    python -m app.reminders_cli 2026-09-02      指定预约日期（开发时拿 GPiS_Dev 的某一天当「明天」）
    python -m app.reminders_cli --check-gpis    检查 GPiS 有没有名单要用的栏位（只印栏位名字）、帐号是不是只读的

预约读 GPiS（或 REMINDER_SOURCE=demo 的假资料），诊所设置读本系统的 PostgreSQL。
输出**没有病人名字、电话号码、Remarks**（D44）：号码只印代号（#1、#2 … 同一个号码同一个代号）和种类。
"""

from __future__ import annotations

import sys
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select

from .api.reminders import get_reminder_source
from .db.models import Doctor
from .db.reminders import opted_out_phones
from .db.rules import load_clinic_rules
from .db.session import new_session
from .gpis import GpisReader, NotReadOnlyError, permission_problems
from .reminders import ReminderList, build_reminder_list, clinic_today, reminder_dates


def summary(result: ReminderList, source_label: str) -> list[str]:
    """只有 ID、时间、医生、状态、原因、号码代号。测试会检查这里没有名字和号码。"""
    codes: dict[str | None, str] = {}

    def code(phone: str | None) -> str:
        if phone is None:
            return "-"
        return codes.setdefault(phone, f"#{len(codes) + 1}")

    days = ", ".join(f"{d.isoformat()} ({d:%a})" for d in result.dates)
    ready_lines = sum(len(g.lines) for g in result.ready)
    staff_lines = sum(len(g.lines) for g in result.needs_staff)
    out = [
        f"Source: {source_label}   Dates: {days}",
        f"Ready: {len(result.ready)} numbers / {ready_lines} appointments   "
        f"Needs staff: {len(result.needs_staff)} numbers / {staff_lines} appointments",
        "Not appointments: " + (", ".join(f"{r} {n}" for r, n in result.not_appointments) or "none"),
        "",
        f"{'List':<12}{'Date':<12}{'Phone':<7}{'Kind':<15}{'AppointmentIDs':<18}{'Time':<7}{'Doctor':<8}"
        f"{'Status':<11}Reasons",
    ]
    for name, groups in (("READY", result.ready), ("NEEDS_STAFF", result.needs_staff)):
        for g in groups:
            for i, ln in enumerate(g.lines):
                ids = ",".join(str(x) for x in ln.appointment_ids)
                reasons = "; ".join(g.problems) if i == 0 else ""
                out.append(
                    f"{name:<12}{g.day.isoformat():<12}{code(g.phone):<7}{g.phone_kind.value:<15}{ids:<18}"
                    f"{ln.slot.strftime('%H:%M') if ln.slot else '?':<7}{ln.doctor_id:<8}"
                    f"{(ln.status or '')[:10]:<11}{reasons}"
                )
    return out


def check_gpis() -> int:
    source = get_reminder_source()
    if not isinstance(source, GpisReader):
        print("REMINDER_SOURCE=demo：不连 GPiS，没有东西要检查。")
        return 0
    try:
        missing = source.missing_columns()
        perms = source.permissions()
    except NotReadOnlyError as e:
        print(f"[!!] {e}")
        print("     GPIS_CONNECTION_STRING 要用只读帐号（UID=chatbot_reader），见 sql/README.md「只读帐号」。")
        return 1
    if missing:
        print("[!!] GPiS 少了这些栏位（把这几行贴回来，程序要改）：")
        for m in missing:
            print(f"     {m}")
        return 1
    print(f"[OK] {source.label} 有提醒名单要用的全部栏位。")

    problems, warnings = permission_problems(perms)
    if problems:
        print(f"[!!] 帐号 {perms.LoginName} 不是只读的：")
        for p in problems:
            print(f"     {p}")
        print("     读主机的 GPiS 时系统会拒绝。开发电脑用 Windows 帐号（Trusted_Connection）连 GPiS_Dev 时，看到这个是正常的。")
    else:
        print(f"[OK] 帐号 {perms.LoginName} 是只读的：读得到预约，读不到 Tbl_User，不能写、不能备份。")
    for w in warnings:
        print(f"[提醒] {w}")
    return 1 if problems and source.is_production else 0


def main(argv: list[str]) -> int:
    try:
        return _run(argv)
    except HTTPException as e:      # 例：没有设置 GPIS_CONNECTION_STRING
        print(e.detail)
        return 1


def _run(argv: list[str]) -> int:
    if argv == ["--check-gpis"]:
        return check_gpis()
    if len(argv) > 1 or (argv and argv[0].startswith("-")):
        print(__doc__)
        return 2
    with new_session() as session:
        rules = load_clinic_rules(session)
        doctor_names = {d.id: d.display_name for d in session.scalars(select(Doctor))}
        opted_out = opted_out_phones(session)
    dates = [date.fromisoformat(argv[0])] if argv else reminder_dates(clinic_today(), rules.closures)
    source = get_reminder_source()
    rows = source.reminder_appointments(min(dates), max(dates))
    print("\n".join(summary(build_reminder_list(dates, rows, rules, doctor_names, opted_out=opted_out), source.label)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
