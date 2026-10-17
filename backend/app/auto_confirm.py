"""自动确认（Phase 6a-2c，D71 ②、D74）：系统自己去 GPiS 找员工约好的预约。

Settings 的开关 auto_confirm 默认关、只有 ADMIN 能改。打开后 Admin API（电脑 B 的 uvicorn）营业时间每 3 分钟：
1. 读还在 PENDING、病人已经有 GPiS ContactID、有日期 / 时段 / 医生、日期还没过的请求那几天的 GPiS 预约（只读）。
2. 第一次看到一个请求时，先记下那天这位病人在 GPiS 已经有没有预约（gpis_same_day_before）：
   已经有 → 这个请求只能员工按（可能是旧的预约，免得没人看过就确认）；没有 → 之后出现的才算。
3. 下面全部一样，而且只有一个预约对得上、这个预约也只对得上这一个请求，才自动 CONFIRMED、马上通知病人：
   同一位病人（ContactID）、同一天、同一个时段、同一位医生、Remarks 有请求的疗程代码、时长一样（1HOUR ↔ 60 分钟）、
   还没确认别的请求。对不上的照样留在 Pending，等员工按 Entered in GPiS ✓（D71 ①）。
4. 每次成功读到 GPiS 记下时间（Requests 页面显示「上次查 GPiS」，营业时间超过 15 分钟没成功就红字）。

读 GPiS_Dev 时不跑（名字是真的病人，不能把真的预约接到假资料上，D44）。Remarks 只在内存里比对，不存、不印。

用法（在 backend/ 里，先启用 venv）：
    python -m app.auto_confirm --dry-run     读一次 GPiS，只印出会怎么做（不改资料；不管开关、营业时间）
    python -m app.auto_confirm --once        马上真的跑一次（开关要打开；不管营业时间）
印出来的只有请求编号、日期、时间、医生，没有名字、号码、Remarks。
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .availability import duration_slots, normalize_remarks
from .confirm import GpisChoice, gpis_choices, may_send
from .confirming import confirm_choice, used_by
from .db.models import AppointmentRequest, ClinicSettings, Customer, RequestStatus
from .reminders import CLINIC_TZ, ReminderAppointment, ReminderSource
from .whatsapp import WhatsAppClient

log = logging.getLogger(__name__)

INTERVAL = timedelta(minutes=3)
BUSINESS_START, BUSINESS_END = time(9, 0), time(17, 30)       # D70：员工只在上班时输入 GPiS
STALE_AFTER = timedelta(minutes=15)                           # 营业时间超过这么久没成功查 GPiS → 页面红字
_LOCK_KEY = 642_017                                           # 两个 Admin API 同时开时，只有一个在跑（D19）


def in_business_hours(now: datetime) -> bool:
    t = now.astimezone(CLINIC_TZ).time()
    return BUSINESS_START <= t < BUSINESS_END


def has_treatment(remarks: str | None, code: str) -> bool:
    """Remarks 有这个疗程代码（前后不是字母、数字；代码里的空格可有可无）。例 S+P → `S+P (P) WITH` 有、`ORS+P2` 没有。"""
    parts = [re.escape(p) for p in code.strip().upper().split()]
    if not parts:
        return False
    pattern = r"(?<![A-Z0-9])" + r"\s*".join(parts) + r"(?![A-Z0-9])"
    return re.search(pattern, (remarks or "").upper()) is not None


@dataclass(frozen=True)
class PendingFacts:
    """拿来比对的请求资料（没有名字）。"""

    request_id: int
    contact_id: int
    day: date
    slot: time
    doctor_id: str
    service_code: str
    duration_minutes: int
    same_day_before: bool | None


@dataclass
class Plan:
    baselines: dict[int, bool] = field(default_factory=dict)       # 第一次看：请求编号 → 那天已经有预约
    matches: dict[int, GpisChoice] = field(default_factory=dict)   # 可以自动确认的：请求编号 → GPiS 预约


def plan(
    pending: list[PendingFacts], rows: list[ReminderAppointment], used: set[int], clinic_contact_id: int
) -> Plan:
    """决定这一次要做什么（只计算，不改资料）。"""
    result = Plan()
    remarks = {a.appointment_id: a.remarks for a in rows}
    by_patient_day: dict[tuple[int | None, date], list[GpisChoice]] = defaultdict(list)
    for c in gpis_choices(rows, clinic_contact_id):
        by_patient_day[(c.contact_id, c.day)].append(c)

    candidates: dict[int, list[GpisChoice]] = {}
    for p in pending:
        same_day = by_patient_day.get((p.contact_id, p.day), [])
        if p.same_day_before is None:
            result.baselines[p.request_id] = bool(same_day)
            continue                                    # 这一次只记下来，下一次才找
        if p.same_day_before:
            continue                                    # 那天本来就有预约：只能员工按
        candidates[p.request_id] = [
            c for c in same_day
            if c.slot == p.slot
            and c.doctor_id == p.doctor_id.upper()
            and c.appointment_id not in used
            and has_treatment(remarks.get(c.appointment_id), p.service_code)
            and duration_slots(normalize_remarks(remarks.get(c.appointment_id))) == max(p.duration_minutes // 30, 1)
        ]

    wanted: dict[int, int] = defaultdict(int)           # 一个 GPiS 预约对得上几个请求
    for found in candidates.values():
        for c in found:
            wanted[c.appointment_id] += 1
    for request_id, found in candidates.items():
        if len(found) == 1 and wanted[found[0].appointment_id] == 1:
            result.matches[request_id] = found[0]
    return result


@dataclass
class RunResult:
    looked_at: int = 0                                  # 看了几个请求
    first_looks: int = 0                                # 这次第一次看（只记下那天有没有预约）
    confirmed: list[int] = field(default_factory=list)


def _pending_requests(session: Session, today: date, only: set[int] | None) -> list[AppointmentRequest]:
    stmt = (
        select(AppointmentRequest)
        .join(AppointmentRequest.customer)
        .where(
            AppointmentRequest.status == RequestStatus.PENDING,
            Customer.gpis_contact_id.is_not(None),
            AppointmentRequest.preferred_date >= today,
            AppointmentRequest.preferred_slot.is_not(None),
            AppointmentRequest.doctor_id.is_not(None),
        )
        .order_by(AppointmentRequest.id)
    )
    if only is not None:
        stmt = stmt.where(AppointmentRequest.id.in_(only))
    return list(session.scalars(stmt))


def _facts(r: AppointmentRequest) -> PendingFacts:
    return PendingFacts(
        request_id=r.id, contact_id=r.customer.gpis_contact_id, day=r.preferred_date, slot=r.preferred_slot,
        doctor_id=r.doctor_id, service_code=r.service_code, duration_minutes=r.duration_minutes,
        same_day_before=r.gpis_same_day_before,
    )


def run_once(
    session: Session,
    source: ReminderSource,
    whatsapp: WhatsAppClient | None,
    now: datetime | None = None,
    *,
    dry_run: bool = False,
    only: set[int] | None = None,
) -> tuple[RunResult, Plan]:
    """跑一次：读 GPiS、记下第一次看到的、自动确认对得上的。GPiS 读不到就 raise（呼叫的人记下错误）。"""
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(CLINIC_TZ).date()
    settings = session.get(ClinicSettings, 1)
    if settings is None:
        raise RuntimeError("Clinic settings are missing: run python -m app.db.seed")
    requests = _pending_requests(session, today, only)
    result = RunResult(looked_at=len(requests))
    if not requests:
        return result, Plan()

    days = [r.preferred_date for r in requests]
    rows = source.reminder_appointments(min(days), max(days))
    used = set(used_by(session, [a.appointment_id for a in rows]))
    decided = plan([_facts(r) for r in requests], rows, used, settings.clinic_contact_id)
    result.first_looks = len(decided.baselines)
    if dry_run:
        session.rollback()
        return result, decided

    by_id = {r.id: r for r in requests}
    for request_id, before in decided.baselines.items():
        by_id[request_id].gpis_same_day_before = before
    session.commit()

    assert whatsapp is not None
    for request_id, choice in decided.matches.items():
        # 锁住那一行再看一次：员工可能刚好同时按了 Entered in GPiS ✓（同一个请求只会确认一次）
        r = session.get(AppointmentRequest, request_id, with_for_update=True, populate_existing=True)
        if r is None or r.status != RequestStatus.PENDING or r.gpis_same_day_before is not False \
                or used_by(session, [choice.appointment_id], request_id):
            session.rollback()
            continue
        confirm_choice(session, r, choice, None, source, whatsapp)
        result.confirmed.append(request_id)
    return result, decided


def record_check(session: Session, error: str | None) -> None:
    """记下这一次查 GPiS 成功了没有（页面显示）。成功一次就清掉错误。"""
    settings = session.get(ClinicSettings, 1)
    if settings is None:
        return
    if error is None:
        settings.auto_confirm_checked_at = func.now()
        settings.auto_confirm_error = None
    else:
        settings.auto_confirm_error = error[:300]
    session.commit()


@dataclass(frozen=True)
class Status:
    enabled: bool
    runs_here: bool              # 这台电脑的资料来源可以自动确认（读主机的 GPiS 或假资料）
    source: str | None
    checked_at: datetime | None
    error: str | None
    in_business_hours: bool
    stale: bool                  # 打开了、营业时间，但超过 15 分钟没成功查 GPiS


def status(settings: ClinicSettings, source: ReminderSource | None, now: datetime | None = None) -> Status:
    now = now or datetime.now(timezone.utc)
    runs_here = source is not None and may_send(source)
    hours = in_business_hours(now)
    checked = settings.auto_confirm_checked_at
    stale = settings.auto_confirm and runs_here and hours and (checked is None or now - checked > STALE_AFTER)
    return Status(
        enabled=settings.auto_confirm, runs_here=runs_here, source=source.label if source else None,
        checked_at=checked, error=settings.auto_confirm_error, in_business_hours=hours, stale=stale,
    )


# ---------- 在 Admin API 里每 3 分钟跑一次 ----------

def _source_or_none() -> ReminderSource | None:
    from .api.requests import get_confirm_source

    return get_confirm_source()


def tick(now: datetime | None = None) -> RunResult | None:
    """背景执行一次：开关打开、营业时间、来源可以自动确认才跑。回传 None = 这一次没跑。"""
    from .db.session import new_session
    from .whatsapp import get_whatsapp_client

    now = now or datetime.now(timezone.utc)
    if not in_business_hours(now):
        return None
    with new_session() as session:
        settings = session.get(ClinicSettings, 1)
        if settings is None or not settings.auto_confirm:
            return None
        source = _source_or_none()
        if source is None or not may_send(source):
            return None
        # 用另一条连线拿锁：session 每次 commit 可能换连线，锁要一直在同一条连线上
        bind = session.get_bind()
        with getattr(bind, "engine", bind).connect() as lock_conn:
            if not lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _LOCK_KEY}).scalar():
                return None                              # 另一个 Admin API 正在跑
            try:
                try:
                    result, _ = run_once(session, source, get_whatsapp_client(), now)
                except Exception as e:
                    session.rollback()
                    log.exception("自动确认：读 GPiS 或确认失败")
                    record_check(session, f"Could not check GPiS ({type(e).__name__}). See the server log.")
                    return None
                record_check(session, None)
                if result.confirmed:
                    log.info("自动确认：确认了 %d 个请求 %s", len(result.confirmed), result.confirmed)
                return result
            finally:
                lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY})


class Loop:
    """Admin API 启动时开始、关掉时停（app/main.py 的 lifespan）。第一次在启动后 20 秒。"""

    def __init__(self, interval: timedelta = INTERVAL, first_after: float = 20.0):
        self.interval, self.first_after = interval, first_after
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="auto-confirm", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        wait = self.first_after
        while not self._stop.wait(wait):
            try:
                tick()
            except Exception:                            # 例：PostgreSQL 没开。下一次再试
                log.exception("自动确认：这一次没有跑成")
            wait = self.interval.total_seconds()


# ---------- 终端 ----------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.auto_confirm", description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="只印出会怎么做，不改资料")
    mode.add_argument("--once", action="store_true", help="马上真的跑一次（开关要打开）")
    args = parser.parse_args(argv)

    from .db.session import new_session
    from .whatsapp import get_whatsapp_client

    source = _source_or_none()
    if source is None:
        print("GPiS is not set up (GPIS_CONNECTION_STRING), and REMINDER_SOURCE is not demo.")
        return 1
    if not may_send(source):
        print(f"Auto-confirm does not run on {source.label}: it has real patient names (D44). "
              "Use REMINDER_SOURCE=demo or the clinic's GPiS.")
        return 1
    with new_session() as session:
        settings = session.get(ClinicSettings, 1)
        if args.once and (settings is None or not settings.auto_confirm):
            print("Auto-confirm is off: an admin turns it on in Settings → Slots & auto-confirm.")
            return 1
        result, decided = run_once(session, source, None if args.dry_run else get_whatsapp_client(),
                                   dry_run=args.dry_run)
        if args.once:
            record_check(session, None)
    print(f"Source: {source.label}. Pending requests looked at: {result.looked_at}.")
    for request_id, before in sorted(decided.baselines.items()):
        print(f"  request {request_id}: first look, patient already has an appointment that day = {before}"
              + ("  (staff must confirm this one)" if before else ""))
    for request_id, c in sorted(decided.matches.items()):
        verb = "would confirm" if args.dry_run else ("confirmed" if request_id in result.confirmed else
                                                      "skipped (changed meanwhile)")
        print(f"  request {request_id}: {verb} GPiS appointment {c.appointment_id} "
              f"({c.day:%Y-%m-%d} {c.slot:%H:%M} Dr {c.doctor_id})")
    if not decided.baselines and not decided.matches:
        print("  nothing to do")
    return 0


if __name__ == "__main__":
    sys.exit(main())
