"""删掉保留期限过了的病人资料（A10、D67），只印日期和数目。

电脑 B：每次登入 Windows 时由 deploy/start-chatbot.ps1 执行（开机备份成功之后、启动 uvicorn 之前）。

用法（在 backend/ 里）：
    python -m app.retention              删掉预约日期早于「今天 − 90 天」的提醒（每天的数目留在 reminder_stats），
                                         还有改回照常提醒、没有对话的号码
    python -m app.retention --dry-run    只印会删几条，什么都不删
    python -m app.retention --stats      每个月的数目（还在的提醒、已经删掉只留数目的都算）

输出没有病人名字、号码（可以贴给 AI 看）。
"""

from __future__ import annotations

import sys
from datetime import date

from .db.retention import RETENTION_DAYS, DayCounts, PurgeResult, daily_counts, purge_old_reminders, retention_cutoff
from .db.session import new_session
from .reminders import clinic_today


def purge_summary(r: PurgeResult, dry_run: bool) -> str:
    before = f"预约日期在 {r.cutoff.isoformat()} 之前的提醒"
    if dry_run:
        return f"只看、不删：{before}有 {r.reminders} 条（{r.days} 天）；不用再留的号码有 {r.contacts} 个"
    return (f"清理：{before}删了 {r.reminders} 条（{r.days} 天，每天的数目留在 reminder_stats）；"
            f"不用再留的号码删了 {r.contacts} 个")


def stats_lines(days: dict[date, DayCounts], cutoff: date) -> list[str]:
    months: dict[str, tuple[int, DayCounts]] = {}
    for day in sorted(days):
        n, total = months.get(day.strftime("%Y-%m"), (0, DayCounts()))
        total.add(days[day])
        months[day.strftime("%Y-%m")] = (n + 1, total)
    out = [
        f"提醒记录保留 {RETENTION_DAYS} 天：预约日期在 {cutoff.isoformat()} 之前的只留每天的数目（A10）",
        f"{'Month':<9}{'Days':>6}{'Opened':>8}{'NotSent':>9}{'Appointments':>14}",
    ]
    all_days, grand = 0, DayCounts()
    for month, (n, c) in months.items():
        out.append(f"{month:<9}{n:>6}{c.opened:>8}{c.not_sent:>9}{c.opened_appointments:>14}")
        all_days += n
        grand.add(c)
    out.append(f"{'Total':<9}{all_days:>6}{grand.opened:>8}{grand.not_sent:>9}{grand.opened_appointments:>14}")
    return out


def main(argv: list[str]) -> int:
    if argv not in ([], ["--dry-run"], ["--stats"]):
        print(__doc__)
        return 2
    today = clinic_today()
    with new_session() as session:
        if argv == ["--stats"]:
            print("\n".join(stats_lines(daily_counts(session), retention_cutoff(today))))
            return 0
        dry_run = argv == ["--dry-run"]
        result = purge_old_reminders(session, today, dry_run=dry_run)
        if not dry_run:
            session.commit()      # 全部做完才 commit：中间出错就一条都不删
    print(purge_summary(result, dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
