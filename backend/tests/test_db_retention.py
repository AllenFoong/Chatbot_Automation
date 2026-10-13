"""病人资料留多久（A10、D67）：过了 90 天的提醒删掉、只留每天的数目。全部假号码、假名字。"""

from contextlib import contextmanager
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app import retention as cli
from app.db import retention
from app.db.models import Conversation, OptOutBy, Reminder, ReminderStats, ReminderStatus, WaContact
from app.db.retention import DayCounts, daily_counts, purge_old_reminders, retention_cutoff
from tests.database import add_staff

TODAY = date(2026, 10, 13)
CUTOFF = date(2026, 7, 15)          # 今天 − 90 天：这一天的留着，前一天的删掉
OLD = CUTOFF - timedelta(days=1)
OLDER = CUTOFF - timedelta(days=30)
NAME = "DEMO PATIENT A"


def add_reminder(session, day, phone="60120000001", status=ReminderStatus.OPENED, ids=(1,)):
    r = Reminder(appointment_date=day, wa_phone=phone, status=status, body=f"NAME: {NAME}",
                 gpis_appointment_ids=list(ids))
    session.add(r)
    session.flush()
    return r


def remaining_days(session):
    return sorted(session.scalars(select(Reminder.appointment_date)))


def stats(session):
    return {s.appointment_date: (s.opened, s.not_sent, s.opened_appointments)
            for s in session.scalars(select(ReminderStats))}


def test_cutoff_is_90_days_and_at_least_30():
    assert retention_cutoff(TODAY) == CUTOFF
    # B 从 2026-10-13 才开始记：10-14 的预约在 2027-01-13 第一次被删
    assert retention_cutoff(date(2027, 1, 12)) == date(2026, 10, 14)
    assert retention_cutoff(date(2027, 1, 13)) == date(2026, 10, 15)
    assert retention_cutoff(TODAY, 30) == TODAY - timedelta(days=30)
    with pytest.raises(ValueError):
        retention_cutoff(TODAY, 29)


def test_every_status_is_counted():
    """加了新的状态（5c），统计也要一起加，不然删的时候会出错。"""
    assert set(retention._COUNTED_AS) == set(ReminderStatus)


def test_old_reminders_are_deleted_and_counted(session):
    add_reminder(session, OLDER, "60120000001", ids=(11, 12))
    add_reminder(session, OLDER, "60120000002", ReminderStatus.NOT_SENT, ids=(13,))
    add_reminder(session, OLD, "60120000001", ids=(14,))
    add_reminder(session, CUTOFF, "60120000001")                   # 刚好 90 天前：留着
    add_reminder(session, TODAY + timedelta(days=1), "60120000001")  # 明天：留着

    result = purge_old_reminders(session, TODAY)

    assert (result.cutoff, result.reminders, result.days) == (CUTOFF, 3, 2)
    assert remaining_days(session) == [CUTOFF, TODAY + timedelta(days=1)]
    # NOT_SENT 的预约不算进 opened_appointments
    assert stats(session) == {OLDER: (1, 1, 2), OLD: (1, 0, 1)}


def test_purging_again_adds_up(session):
    add_reminder(session, OLD, "60120000001", ids=(1, 2))
    purge_old_reminders(session, TODAY)
    assert purge_old_reminders(session, TODAY).reminders == 0       # 再跑一次：没有东西删，数目不变
    assert stats(session) == {OLD: (1, 0, 2)}
    # 员工选了很久以前的日子再按 Open：之后删的时候数目累加，不会盖掉
    add_reminder(session, OLD, "60120000002", ids=(3,))
    purge_old_reminders(session, TODAY)
    assert stats(session) == {OLD: (2, 0, 3)}


def test_dry_run_deletes_nothing(session):
    add_reminder(session, OLD)
    session.add(WaContact(wa_phone="60120000009"))
    session.flush()
    result = purge_old_reminders(session, TODAY, dry_run=True)
    assert (result.reminders, result.days, result.contacts) == (1, 1, 1)
    assert remaining_days(session) == [OLD]
    assert stats(session) == {}
    assert session.scalar(select(func.count()).select_from(WaContact)) == 1


def test_only_unused_numbers_are_deleted(session):
    staff = add_staff(session)
    opted_out = WaContact(wa_phone="60120000001", reminders_opt_out_at=func.now(),
                          reminders_opt_out_by=OptOutBy.STAFF, reminders_opt_out_staff_id=staff.id)
    allowed_again = WaContact(wa_phone="60120000002")               # 按过 NO WA，又改回照常提醒
    with_conversation = WaContact(wa_phone="60120000003")
    session.add_all([opted_out, allowed_again, with_conversation])
    session.flush()
    session.add(Conversation(wa_contact_id=with_conversation.id))
    session.flush()

    assert purge_old_reminders(session, TODAY).contacts == 1
    assert sorted(session.scalars(select(WaContact.wa_phone))) == ["60120000001", "60120000003"]


def test_daily_counts_include_kept_and_deleted(session):
    add_reminder(session, OLD, "60120000001", ids=(1, 2))
    purge_old_reminders(session, TODAY)
    add_reminder(session, TODAY, "60120000001", ids=(3,))
    add_reminder(session, TODAY, "60120000002", ReminderStatus.NOT_SENT)
    assert daily_counts(session) == {OLD: DayCounts(1, 0, 2), TODAY: DayCounts(1, 1, 1)}


# ---------- 终端程序（python -m app.retention） ----------

@pytest.fixture
def run_cli(session, monkeypatch, capsys):
    """在测试数据库跑 main()。离开 with 时 rollback（和真的 new_session() 关掉时一样）：没有 commit 的都不算。"""

    @contextmanager
    def test_session():
        try:
            yield session
        finally:
            session.rollback()

    monkeypatch.setattr(cli, "new_session", test_session)
    monkeypatch.setattr(cli, "clinic_today", lambda: TODAY)

    def run(*argv):
        code = cli.main(list(argv))
        return code, capsys.readouterr().out

    return run


def test_cli_deletes_and_prints_only_dates_and_counts(session, run_cli):
    add_reminder(session, OLD, "60120000001")
    code, out = run_cli()
    assert code == 0
    assert out.strip() == ("清理：预约日期在 2026-07-15 之前的提醒删了 1 条（1 天，每天的数目留在 reminder_stats）；"
                           "不用再留的号码删了 0 个")
    assert "60120000001" not in out and NAME not in out
    assert remaining_days(session) == [] and stats(session) == {OLD: (1, 0, 1)}


def test_cli_dry_run(session, run_cli):
    add_reminder(session, OLD)
    session.commit()
    code, out = run_cli("--dry-run")
    assert code == 0 and out.startswith("只看、不删：") and "有 1 条" in out
    assert remaining_days(session) == [OLD]


def test_cli_deletes_nothing_when_something_fails(session, run_cli, monkeypatch):
    """统计写不进去 → 没有 commit，一条都没删。"""
    add_reminder(session, OLD)
    session.commit()

    def broken(*args):
        raise RuntimeError("stats failed")

    monkeypatch.setattr(retention, "_add_to_stats", broken)
    with pytest.raises(RuntimeError):
        run_cli()
    assert remaining_days(session) == [OLD]


def test_cli_stats_by_month(session, run_cli):
    add_reminder(session, OLD, "60120000001", ids=(1, 2))
    add_reminder(session, date(2026, 10, 1), "60120000001")
    add_reminder(session, date(2026, 10, 2), "60120000002", ReminderStatus.NOT_SENT)
    purge_old_reminders(session, TODAY)
    session.commit()
    code, out = run_cli("--stats")
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "提醒记录保留 90 天：预约日期在 2026-07-15 之前的只留每天的数目（A10）"
    assert lines[2].split() == ["2026-07", "1", "1", "0", "2"]
    assert lines[3].split() == ["2026-10", "2", "1", "1", "1"]
    assert lines[4].split() == ["Total", "3", "2", "1", "3"]
    assert "60120000001" not in out and NAME not in out


def test_cli_rejects_unknown_arguments(run_cli):
    code, out = run_cli("--all")
    assert code == 2 and "用法" in out
