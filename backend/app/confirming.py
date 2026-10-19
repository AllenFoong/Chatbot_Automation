"""确认一个请求、通知病人：员工按 Entered in GPiS ✓（D71 ①）和系统自动确认（D71 ②、6a-2c）共用。

- 先存 CONFIRMED 再发：中途当机的留在「要通知」，不自动重发（病人可能已经收到，D45）。
- 发不了的（读 GPiS_Dev、没有对话、超过 24 小时、对话已结束、允许名单、没设定 WhatsApp …）写原因，留在「要通知」。
- 确认消息照 GPiS 的名字、日期、时间、医生（D73）。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_reminder_text
from .confirm import GpisChoice, may_send, render_confirmation
from .db import appointment_requests as reqs
from .db import conversations as conv
from .db.models import AppointmentRequest, ConversationMode, Customer, Doctor, RequestStatus, Sender, Staff, WaStatus
from .reminders import ReminderSource
from .whatsapp import RecipientNotAllowed, WhatsAppClient, WhatsAppError, WhatsAppNotConfigured

log = logging.getLogger(__name__)


def used_by(session: Session, appointment_ids: list[int], request_id: int | None = None) -> dict[int, int]:
    """这些 GPiS 预约已经确认了哪个请求（{AppointmentID: 请求编号}）。一个 GPiS 预约只能确认一个请求。"""
    if not appointment_ids:
        return {}
    stmt = select(AppointmentRequest.gpis_appointment_id, AppointmentRequest.id).where(
        AppointmentRequest.status == RequestStatus.CONFIRMED,
        AppointmentRequest.gpis_appointment_id.in_(appointment_ids),
    )
    if request_id is not None:
        stmt = stmt.where(AppointmentRequest.id != request_id)
    return {gpis_id: rid for gpis_id, rid in session.execute(stmt)}


def doctor_names(session: Session) -> dict[str, str]:
    return {d.id: d.display_name for d in session.scalars(select(Doctor))}


def link_contact(session: Session, customer: Customer, contact_id: int | None) -> None:
    """新病人：记下 GPiS 的 ContactID，下次就认得（D71）。已经有、或别的病人用了这个 ID，就不改。"""
    if customer.gpis_contact_id is not None or contact_id is None:
        return
    taken = session.scalar(select(Customer.id).where(Customer.gpis_contact_id == contact_id))
    if taken is None:
        customer.gpis_contact_id = contact_id


def notify(
    session: Session, r: AppointmentRequest, source: ReminderSource, whatsapp: WhatsAppClient, staff: Staff | None
) -> None:
    """确认之后马上经 WhatsApp 通知病人；发不了就留在「要通知」，写原因。"""
    message = r.confirm_message or ""
    if not may_send(source):
        reqs.notify_failed(session, r, f"Not sent: the GPiS list comes from {source.label} (test data with real "
                                       "patient names). Use demo data or the clinic's GPiS to send.")
        return
    if r.conversation is None:
        reqs.notify_failed(session, r, "No WhatsApp conversation (the request was added by staff)")
        return
    contact = r.conversation.wa_contact
    if not conv.customer_service_window_open(session, contact.id):
        reqs.notify_failed(session, r, "More than 24 hours since the patient's last message: WhatsApp only allows "
                                       "approved templates now")
        return
    open_conversation = conv.get_open_conversation(session, contact.id)
    if open_conversation is None:
        reqs.notify_failed(session, r, "The WhatsApp conversation is closed")
        return
    try:
        wa_message_id = whatsapp.send_text(contact.wa_phone, message)
    except RecipientNotAllowed:
        reqs.notify_failed(session, r, "This number is not in WHATSAPP_ALLOWED_RECIPIENTS (development)")
        return
    except WhatsAppNotConfigured:
        reqs.notify_failed(session, r, "WhatsApp is not set up on this computer")
        return
    except WhatsAppError as e:
        reqs.notify_failed(session, r, f"WhatsApp did not accept the message: {e}")
        return
    try:
        # AI 在回复的对话：算 AI（系统）发的，AI 照常继续；员工接手的对话：算员工发的（不会变成接手）。
        # 系统自动确认（staff = None）在员工接手的对话里，记成员工发的、不知道是哪一位
        if open_conversation.mode == ConversationMode.BOT:
            conv.record_outgoing_message(session, open_conversation, Sender.BOT, message,
                                         wa_message_id=wa_message_id, wa_status=WaStatus.ACCEPTED)
        else:
            conv.record_outgoing_message(session, open_conversation, Sender.STAFF, message, staff=staff,
                                         wa_message_id=wa_message_id, wa_status=WaStatus.ACCEPTED)
        reqs.patient_notified(session, r)
        session.commit()
    except Exception:
        # 病人已经收到了，但记录没存进去：留下消息 ID，方便查；请求留在「要通知」
        log.exception("确认消息已经发出，但存进数据库失败（%s）", wa_message_id)
        session.rollback()
        reqs.notify_failed(session, r, "The message was sent, but saving it failed. Check the WhatsApp chat "
                                       "before telling the patient again.")


def confirm_choice(
    session: Session,
    r: AppointmentRequest,
    choice: GpisChoice,
    staff: Staff | None,
    source: ReminderSource,
    whatsapp: WhatsAppClient,
) -> None:
    """确认 r = GPiS 的这个预约（staff = None：系统自动确认），然后通知病人。会 commit。

    呼叫的人要先锁住 r、确认还是 PENDING、这个 GPiS 预约还没确认别的请求。
    """
    names = doctor_names(session)
    message = render_confirmation(choice, names.get(choice.doctor_id, choice.doctor_id), get_reminder_text())
    link_contact(session, r.customer, choice.contact_id)
    reqs.confirm_request(
        session, r, staff, choice.appointment_id,
        confirmed_date=choice.day, confirmed_slot=choice.slot, confirmed_doctor_id=choice.doctor_id,
        confirm_message=message,
    )
    session.commit()                                   # 先存 CONFIRMED，再发：中途当机的留在「要通知」
    notify(session, r, source, whatsapp, staff)
    session.commit()
