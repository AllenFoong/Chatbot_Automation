"""每 3 分钟找 GPiS 的预约，把对上的 PENDING 请求改成 CONFIRMED、通知病人（D70，docs/architecture.md 11.6）。

- 只在营业时间（马来西亚时间 9:00–17:30）找；只读那几个请求日期、那几位病人的预约（gpis.py MATCH_SQL，只读帐号）。
- 对得上的规则在 app/matching.py。新病人（还没有 ContactID）、改了时间的、对得上两个的：不自动，员工按。
- 确认之后：病人最后一条消息在 24 小时内 → 系统经 WhatsApp 发确认；不然（或这台电脑没接 WhatsApp、发不出去）
  → 记下原因，Requests 页面标「要通知」，员工自己通知后按 Patient told ✓。
- 资料从哪里来和提醒一样（REMINDER_SOURCE：gpis / demo）。
- 跟着 Admin API（uvicorn app.main:app）一起跑；REQUEST_MATCHER=off 就不跑。
- 日志只记请求编号和数目，不记名字、号码、消息内容（D38）。

手动跑一次（不管营业时间）：python -m app.request_matcher --once（--dry-run 只看找到几个，不改、不发）
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_reminder_text, get_settings, reminder_source_name, request_matcher_enabled
from .db import conversations as conv
from .db.appointment_requests import confirm_found_in_gpis, mark_patient_notified
from .db.models import AppointmentRequest, Customer, Doctor, RequestStatus, Sender, WaStatus
from .db.rules import load_clinic_rules
from .matching import RequestToMatch, find_matches, render_confirmation
from .reminders import CLINIC_TZ, ReminderText, clinic_today
from .whatsapp import RecipientNotAllowed, WhatsAppError, WhatsAppNotConfigured

log = logging.getLogger(__name__)

INTERVAL_SECONDS = 180
BUSINESS_START = time(9, 0)
BUSINESS_END = time(17, 30)

# 系统发不了确认的原因（给员工看，英文，D24）
NO_CONVERSATION = "Not from a WhatsApp conversation"
CONVERSATION_CLOSED = "The conversation is closed"
WINDOW_CLOSED = "More than 24 hours since the patient's last message"
NOT_CONNECTED = "WhatsApp is not connected on this computer"
NOT_ALLOWED = "Number not in WHATSAPP_ALLOWED_RECIPIENTS"


def in_business_hours(now: datetime | None = None) -> bool:
    local = (now or datetime.now(timezone.utc)).astimezone(CLINIC_TZ).time()
    return BUSINESS_START <= local < BUSINESS_END


@dataclass
class MatchResult:
    requests: int = 0                                     # 找了几个请求
    days: int = 0                                         # 读了 GPiS 几天
    confirmed: list[int] = field(default_factory=list)    # 自动确认的请求编号
    notified: list[int] = field(default_factory=list)     # 系统发了确认的
    to_notify: list[int] = field(default_factory=list)    # 要员工通知的

    def summary(self) -> str:
        return (f"找了 {self.requests} 个请求（读了 GPiS {self.days} 天）：自动确认 {len(self.confirmed)} 个，"
                f"系统发了确认 {len(self.notified)} 个，要员工通知 {len(self.to_notify)} 个")


def requests_to_match(session: Session, today: date) -> list[RequestToMatch]:
    """今天以后、有时段和医生、病人有 ContactID 的 PENDING 请求。"""
    rows = session.execute(
        select(AppointmentRequest.id, Customer.gpis_contact_id, AppointmentRequest.preferred_date,
               AppointmentRequest.preferred_slot, AppointmentRequest.doctor_id)
        .join(AppointmentRequest.customer)
        .where(
            AppointmentRequest.status == RequestStatus.PENDING,
            AppointmentRequest.preferred_date >= today,
            AppointmentRequest.preferred_slot.is_not(None),
            AppointmentRequest.doctor_id.is_not(None),
            Customer.gpis_contact_id.is_not(None),
        )
        .order_by(AppointmentRequest.id)
    )
    return [RequestToMatch(r.id, r.gpis_contact_id, r.preferred_date, r.preferred_slot, r.doctor_id) for r in rows]


def find_in_gpis(session: Session, source, today: date, clinic_contact_id: int,
                 result: MatchResult) -> dict[int, int]:
    """{request_id: GPiS AppointmentID}。读 GPiS 失败就整个停下来（raise），什么都不改。"""
    pending = requests_to_match(session, today)
    result.requests = len(pending)
    by_day: dict[date, list[RequestToMatch]] = defaultdict(list)
    for r in pending:
        by_day[r.day].append(r)
    result.days = len(by_day)

    matches: dict[int, int] = {}
    for day, reqs in sorted(by_day.items()):
        appointments = source.patient_appointments(day, {r.contact_id for r in reqs})
        ids = {a.appointment_id for a in appointments}
        linked = set(session.scalars(
            select(AppointmentRequest.gpis_appointment_id).where(AppointmentRequest.gpis_appointment_id.in_(ids))
        )) if ids else set()
        matches.update(find_matches(reqs, appointments, clinic_contact_id, linked))
    return matches


def confirm_matches(session: Session, matches: dict[int, int], result: MatchResult) -> None:
    for request_id, appointment_id in sorted(matches.items()):
        # 锁住这一行：员工同时按确认的话，只有一边改得到（另一边看到不是 PENDING 了）
        r = session.scalars(
            select(AppointmentRequest).where(AppointmentRequest.id == request_id)
            .with_for_update(skip_locked=True)
        ).one_or_none()
        if r is None or r.status != RequestStatus.PENDING:
            continue
        try:
            with session.begin_nested():
                confirm_found_in_gpis(session, r, appointment_id)
        except IntegrityError:          # 这个 GPiS 预约刚好被别的请求用了
            session.refresh(r)
            continue
        result.confirmed.append(request_id)
    session.commit()


def notify_patient(session: Session, request: AppointmentRequest, whatsapp, text: ReminderText) -> str | None:
    """经 WhatsApp 发确认给病人。发了回 None；发不了回原因（记在 notify_problem，员工自己通知）。"""
    if request.conversation is None:
        return NO_CONVERSATION
    contact_id = request.conversation.wa_contact_id
    conversation = conv.get_open_conversation(session, contact_id)
    if conversation is None:
        return CONVERSATION_CLOSED
    if not conv.customer_service_window_open(session, contact_id):
        return WINDOW_CLOSED

    doctor = session.get(Doctor, request.doctor_id)
    body = render_confirmation(request.customer.name, request.preferred_date, request.preferred_slot,
                               doctor.display_name if doctor else request.doctor_id, text)
    try:
        wa_message_id = whatsapp.send_text(conversation.wa_contact.wa_phone, body)
    except WhatsAppNotConfigured:
        return NOT_CONNECTED
    except RecipientNotAllowed:
        return NOT_ALLOWED
    except WhatsAppError as e:
        return f"WhatsApp did not accept the message: {e}"

    try:
        conv.record_outgoing_message(session, conversation, Sender.BOT, body, wa_message_id=wa_message_id,
                                     wa_status=WaStatus.ACCEPTED, system_notice=True)
        mark_patient_notified(session, request)
    except Exception:
        # 病人已经收到了，但记录没存进去：留下消息 ID，方便查
        log.exception("确认已经发出，但存进数据库失败（请求 %s，%s）", request.id, wa_message_id)
        raise
    return None


def notify_confirmed(session: Session, request_ids: list[int], whatsapp, text: ReminderText,
                     result: MatchResult) -> None:
    """刚刚由系统确认的请求：一个一个发（一个发不了不影响别的）。"""
    for request_id in request_ids:
        r = session.get(AppointmentRequest, request_id)
        if r is None or r.status != RequestStatus.CONFIRMED or r.patient_notified_at is not None:
            continue
        try:
            problem = notify_patient(session, r, whatsapp, text)
        except Exception:
            session.rollback()
            log.exception("通知病人失败（请求 %s）", request_id)
            problem = "The system could not send the confirmation"
            r = session.get(AppointmentRequest, request_id)
        if problem is None:
            result.notified.append(request_id)
        else:
            r.notify_problem = problem
            result.to_notify.append(request_id)
        session.commit()


def matcher_source():
    """和提醒一样（REMINDER_SOURCE）：demo = 假资料，不然读 GPIS_CONNECTION_STRING 的 GPiS。"""
    from .reminder_demo import DemoReminderSource

    if reminder_source_name() == "demo":
        return DemoReminderSource.from_settings()
    from .gpis import GpisReader

    s = get_settings()
    return GpisReader(s.gpis_connection_string, s.gpis_expected_database)


def run_once(session: Session, source, whatsapp, text: ReminderText, today: date | None = None,
             dry_run: bool = False) -> MatchResult:
    result = MatchResult()
    today = today or clinic_today()
    clinic_contact_id = load_clinic_rules(session).clinic_contact_id
    matches = find_in_gpis(session, source, today, clinic_contact_id, result)
    if dry_run:
        result.confirmed = sorted(matches)
        session.rollback()
        return result
    confirm_matches(session, matches, result)
    notify_confirmed(session, result.confirmed, whatsapp, text, result)
    return result


def _run_with_new_session(source=None) -> MatchResult:
    from .db.session import new_session
    from .whatsapp import get_whatsapp_client

    with new_session() as session:
        if not requests_to_match(session, clinic_today()):
            return MatchResult()        # 没有要找的：不连 GPiS
        return run_once(session, source or matcher_source(), get_whatsapp_client(), get_reminder_text())


def run_forever(stop: threading.Event, interval: int = INTERVAL_SECONDS) -> None:
    """营业时间每 interval 秒找一次。出错只记日志，下一次再试（例：GPiS 那台电脑刚好关了）。"""
    while not stop.is_set():
        if in_business_hours():
            try:
                result = _run_with_new_session()
                if result.requests:
                    log.info("找 GPiS 的预约：%s", result.summary())
            except Exception:
                log.exception("找 GPiS 的预约失败，%d 秒后再试", interval)
        stop.wait(interval)


def start_background() -> threading.Event | None:
    """Admin API 启动时呼叫：开一个背景 thread。REQUEST_MATCHER=off 就不开。"""
    if not request_matcher_enabled():
        log.info("REQUEST_MATCHER=off：不自动找 GPiS 的预约")
        return None
    stop = threading.Event()
    threading.Thread(target=run_forever, args=(stop,), name="request-matcher", daemon=True).start()
    return stop


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="找 PENDING 请求在 GPiS 的预约（D70），跑一次（不管营业时间）")
    parser.add_argument("--once", action="store_true", help="跑一次")
    parser.add_argument("--dry-run", action="store_true", help="只看找到几个，不改、不发")
    args = parser.parse_args(argv)
    if not args.once:
        parser.error("要加 --once（平常由 Admin API 每 3 分钟自动跑）")

    from .db.session import new_session
    from .whatsapp import get_whatsapp_client

    with new_session() as session:
        result = run_once(session, matcher_source(), get_whatsapp_client(), get_reminder_text(),
                          dry_run=args.dry_run)
    if args.dry_run:
        print(f"（--dry-run，没有改）找了 {result.requests} 个请求（读了 GPiS {result.days} 天）："
              f"对得上 {len(result.confirmed)} 个")
    else:
        print(result.summary())
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
