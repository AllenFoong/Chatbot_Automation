"""病人资料在本系统留多久（A10、D67）。

- reminders：预约日期早于「今天 − 90 天」的**整行删掉**（号码、填好的消息、预约 ID、员工都不留）；
  删之前把数目加进 reminder_stats（一个预约日期一行，没有号码、名字、员工）。
- wa_contacts：改回照常提醒、又没有对话的号码删掉。按过 NO WA 的**一直留**：删了就会再提醒他（D55）。
- messages、conversations：电脑 B 不收 WhatsApp（D62），留多久和 A9 一起在 5c 之前决定。

这里的函数不 commit：调用的人（app/retention.py）全部做完才 commit，中间出错就一条都不删。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .models import Conversation, Reminder, ReminderStats, ReminderStatus, WaContact

RETENTION_DAYS = 90          # 诊所要改（W60）只改这里
MIN_RETENTION_DAYS = 30      # 防止打错：至少要留到员工回报对不上的、病人来问的时候（D65）

# 每一种状态算进哪一个数目。加新的状态（5c 的 SENDING 等）要一起加，测试会检查
_COUNTED_AS = {ReminderStatus.OPENED: "opened", ReminderStatus.NOT_SENT: "not_sent"}


@dataclass
class DayCounts:
    """一个预约日期的数目（和 reminder_stats 的一行一样）。"""
    opened: int = 0
    not_sent: int = 0
    opened_appointments: int = 0

    def add(self, other: DayCounts) -> None:
        self.opened += other.opened
        self.not_sent += other.not_sent
        self.opened_appointments += other.opened_appointments


@dataclass(frozen=True)
class PurgeResult:
    cutoff: date        # 预约日期早于这一天的删掉
    reminders: int      # 删了（dry_run：会删）几条提醒
    days: int           # 那些提醒有几个预约日期
    contacts: int       # 删了（dry_run：会删）几个号码


def retention_cutoff(today: date, days: int = RETENTION_DAYS) -> date:
    """预约日期早于这一天的提醒要删。例：today = 2026-10-13 → 2026-07-15（7-15 的留着，7-14 的删掉）。"""
    if days < MIN_RETENTION_DAYS:
        raise ValueError(f"保留天数至少要 {MIN_RETENTION_DAYS} 天（现在是 {days}）")
    return today - timedelta(days=days)


def _counts(rows: Iterable[tuple[date, ReminderStatus, list[int]]]) -> dict[date, DayCounts]:
    days: dict[date, DayCounts] = {}
    for day, status, appointment_ids in rows:
        c = days.setdefault(day, DayCounts())
        field = _COUNTED_AS[status]
        setattr(c, field, getattr(c, field) + 1)
        if status == ReminderStatus.OPENED:
            c.opened_appointments += len(appointment_ids)
    return days


def _add_to_stats(session: Session, days: dict[date, DayCounts]) -> None:
    """加上去，不是盖过去：同一个预约日期之后又删了一条（例：员工选了很久以前的日子按 Open），数目累加。"""
    if not days:
        return
    stmt = insert(ReminderStats).values([
        dict(appointment_date=d, opened=c.opened, not_sent=c.not_sent, opened_appointments=c.opened_appointments)
        for d, c in sorted(days.items())
    ])
    table = ReminderStats.__table__.c
    session.execute(stmt.on_conflict_do_update(
        index_elements=["appointment_date"],
        set_={
            "opened": table.opened + stmt.excluded.opened,
            "not_sent": table.not_sent + stmt.excluded.not_sent,
            "opened_appointments": table.opened_appointments + stmt.excluded.opened_appointments,
        },
    ))


_REMINDER_COLUMNS = (Reminder.appointment_date, Reminder.status, Reminder.gpis_appointment_ids)


def _unused_contact():
    """改回照常提醒、又没有对话的号码：留着没有用处。"""
    return WaContact.reminders_opt_out_at.is_(None) & ~exists().where(Conversation.wa_contact_id == WaContact.id)


def purge_old_reminders(session: Session, today: date, *, dry_run: bool = False) -> PurgeResult:
    """删掉过了保留期限的提醒（数目留在 reminder_stats）和不用再留的号码。dry_run：只算会删几条。"""
    cutoff = retention_cutoff(today)
    old = Reminder.appointment_date < cutoff
    if dry_run:
        rows = session.execute(select(*_REMINDER_COLUMNS).where(old)).all()
        contacts = session.scalar(select(func.count()).select_from(WaContact).where(_unused_contact()))
    else:
        # RETURNING：统计的就是真的删掉的那几行（两个人同时改也不会算错）
        rows = session.execute(
            delete(Reminder).where(old).returning(*_REMINDER_COLUMNS),
            execution_options={"synchronize_session": False},
        ).all()
        _add_to_stats(session, _counts(rows))
        contacts = len(session.execute(
            delete(WaContact).where(_unused_contact()).returning(WaContact.id),
            execution_options={"synchronize_session": False},
        ).all())
        session.expire_all()
    return PurgeResult(cutoff=cutoff, reminders=len(rows), days=len(_counts(rows)), contacts=contacts)


def daily_counts(session: Session) -> dict[date, DayCounts]:
    """每个预约日期的数目：还在的提醒 + 已经删掉、只留在 reminder_stats 的。"""
    days = _counts(session.execute(select(*_REMINDER_COLUMNS)).all())
    for s in session.scalars(select(ReminderStats)):
        days.setdefault(s.appointment_date, DayCounts()).add(
            DayCounts(s.opened, s.not_sent, s.opened_appointments)
        )
    return days
