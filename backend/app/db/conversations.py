"""WhatsApp 对话：收消息、发消息、转人工（docs/architecture.md 第 5 节）。

- 对话按 WhatsApp 号码分；同一个号码同时只有一段没结束的对话（数据库的 unique index 保证）。
- 员工接手（HUMAN）后，AI 不能再回复；员工在 BOT 模式的对话里回复，就等于接手。
- 同一条消息 WhatsApp 可能送来两次：用 wa_message_id 去重，不能让 AI 回复两次。

这里的函数只 flush，不 commit：由调用的人（API / Webhook）在一个交易里决定。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..phone import normalize_phone
from .models import Conversation, ConversationMode, Message, Sender, Staff, WaContact, WaStatus

# WhatsApp 24 小时规则：病人最后一条消息之后 24 小时内才能发一般消息，之后只能发模板消息
CUSTOMER_SERVICE_WINDOW = timedelta(hours=24)


class ConversationError(Exception):
    pass


class ConversationClosed(ConversationError):
    """对话已结束，不能再发消息或改状态。"""


class BotMuted(ConversationError):
    """员工已接手，AI 不能回复（AI 应该安静，等员工处理）。"""


def _insert_or_get(session: Session, obj, existing: Select):
    """新增一行。如果另一个请求刚好先新增了同样的资料（违反 unique），就回传那一行。"""
    try:
        with session.begin_nested():
            session.add(obj)
    except IntegrityError:
        found = session.scalars(existing).one_or_none()
        if found is None:
            raise
        return found
    return obj


def _open_query(wa_contact_id: int) -> Select:
    return select(Conversation).where(
        Conversation.wa_contact_id == wa_contact_id,
        Conversation.mode != ConversationMode.CLOSED,
    )


def get_or_create_wa_contact(session: Session, wa_phone: str, profile_name: str | None = None) -> WaContact:
    phone = normalize_phone(wa_phone)
    if phone is None:
        raise ValueError("看不懂的 WhatsApp 号码")
    query = select(WaContact).where(WaContact.wa_phone == phone)
    contact = session.scalars(query).one_or_none()
    if contact is None:
        contact = _insert_or_get(session, WaContact(wa_phone=phone, profile_name=profile_name), query)
    if profile_name and contact.profile_name != profile_name:
        contact.profile_name = profile_name      # 病人改了 WhatsApp 上的名字
    return contact


def get_open_conversation(session: Session, wa_contact_id: int) -> Conversation | None:
    return session.scalars(_open_query(wa_contact_id)).one_or_none()


def open_conversation(session: Session, contact: WaContact) -> Conversation:
    """这个号码没结束的对话；没有就开一段新的（先由 AI 回复）。"""
    conversation = get_open_conversation(session, contact.id)
    if conversation is None:
        conversation = _insert_or_get(
            session, Conversation(wa_contact_id=contact.id, mode=ConversationMode.BOT), _open_query(contact.id)
        )
    return conversation


def record_incoming_message(
    session: Session, wa_phone: str, body: str, wa_message_id: str, profile_name: str | None = None
) -> tuple[Message, bool]:
    """存一条病人发来的消息，回传 (消息, 是不是新的)。

    不是新的 = WhatsApp 重复送来同一条消息：不要再叫 AI 回复。
    """
    if not wa_message_id:
        raise ValueError("病人的消息一定有 wa_message_id")
    query = select(Message).where(Message.wa_message_id == wa_message_id)
    existing = session.scalars(query).one_or_none()
    if existing is not None:
        return existing, False

    contact = get_or_create_wa_contact(session, wa_phone, profile_name)
    conversation = open_conversation(session, contact)
    message = Message(
        conversation_id=conversation.id, sender=Sender.CUSTOMER, body=body, wa_message_id=wa_message_id
    )
    saved = _insert_or_get(session, message, query)
    return saved, saved is message


def record_outgoing_message(
    session: Session,
    conversation: Conversation,
    sender: Sender,
    body: str,
    staff: Staff | None = None,
    wa_message_id: str | None = None,
    wa_status: WaStatus | None = None,
    system_notice: bool = False,
) -> Message:
    """存一条发给病人的消息。sender = BOT（AI）或 STAFF（员工；staff = None 表示在手机 App 上发的）。

    经 WhatsApp API 发出的，wa_status = ACCEPTED，之后由 status webhook 更新（update_message_status）。
    system_notice：系统自动发的通知（例：预约确认，D70），存成 BOT；员工接手了也照发，不算 AI 回复。
    """
    if sender == Sender.CUSTOMER:
        raise ValueError("病人的消息用 record_incoming_message")
    if sender == Sender.BOT and staff is not None:
        raise ValueError("AI 的消息没有员工")
    _require_open(conversation)
    if system_notice and sender != Sender.BOT:
        raise ValueError("系统的通知存成 BOT")
    if sender == Sender.BOT and conversation.mode == ConversationMode.HUMAN and not system_notice:
        raise BotMuted("员工已接手，AI 不能回复")
    if sender == Sender.STAFF and conversation.mode == ConversationMode.BOT:
        take_over(session, conversation, staff)     # 员工回复 = 接手，AI 停止回复
    elif sender == Sender.STAFF and staff is not None and conversation.assigned_staff_id is None:
        conversation.assigned_staff_id = staff.id   # 转给员工、还没有人负责的对话：谁先回复就由谁负责

    message = Message(
        conversation_id=conversation.id,
        sender=sender,
        staff_id=staff.id if staff else None,
        body=body,
        wa_message_id=wa_message_id,
        wa_status=wa_status,
    )
    session.add(message)
    session.flush()
    return message


# 送到哪一步只会往前走：WhatsApp 的 webhook 不一定照顺序到（可能先收到 read，再收到 delivered）
_STATUS_ORDER = {WaStatus.ACCEPTED: 0, WaStatus.SENT: 1, WaStatus.DELIVERED: 2, WaStatus.READ: 3}


def update_message_status(
    session: Session, wa_message_id: str, status: WaStatus, error: str | None = None
) -> Message | None:
    """WhatsApp 告诉我们一条发出的消息送到哪一步（status webhook）。

    找不到这条消息（不是本系统发的、或还没存进数据库）就不管，回传 None。FAILED 之后不会再变。
    """
    message = session.scalars(select(Message).where(Message.wa_message_id == wa_message_id)).one_or_none()
    if message is None or message.sender == Sender.CUSTOMER or message.wa_status == WaStatus.FAILED:
        return None
    if status == WaStatus.FAILED:
        message.wa_status = WaStatus.FAILED
        message.wa_error = error or "Unknown error"
    elif message.wa_status is None or _STATUS_ORDER[status] > _STATUS_ORDER[message.wa_status]:
        message.wa_status = status
    session.flush()
    return message


def hand_over_to_human(session: Session, conversation: Conversation, reason: str) -> None:
    """AI 转人工（投诉、急症、AI 不确定、病人要求真人 …）。之后 AI 不再回复，等员工处理。"""
    _require_open(conversation)
    conversation.mode = ConversationMode.HUMAN
    conversation.handover_reason = reason
    session.flush()


def take_over(session: Session, conversation: Conversation, staff: Staff | None) -> None:
    """员工接手这段对话，AI 停止回复。"""
    _require_open(conversation)
    conversation.mode = ConversationMode.HUMAN
    if staff is not None:
        conversation.assigned_staff_id = staff.id
    session.flush()


def hand_back_to_bot(session: Session, conversation: Conversation) -> None:
    """员工处理完，让 AI 继续回复。"""
    _require_open(conversation)
    conversation.mode = ConversationMode.BOT
    conversation.assigned_staff_id = None
    conversation.handover_reason = None
    session.flush()


def close_conversation(session: Session, conversation: Conversation) -> None:
    """结束对话。病人之后再发消息，会开一段新的对话。"""
    _require_open(conversation)
    conversation.mode = ConversationMode.CLOSED
    conversation.closed_at = func.now()
    session.flush()


def customer_service_window_ends_at(session: Session, wa_contact_id: int) -> datetime | None:
    """到什么时候还能发一般消息给这个号码（WhatsApp 24 小时规则）；病人从来没发过消息 = None。

    从 messages 算出来，不另外存一栏：不会和消息记录对不上。AI、员工发的消息不会延长 24 小时。
    """
    last = session.scalar(
        select(func.max(Message.created_at))
        .join(Message.conversation)
        .where(Conversation.wa_contact_id == wa_contact_id, Message.sender == Sender.CUSTOMER)
    )
    return None if last is None else last + CUSTOMER_SERVICE_WINDOW


def customer_service_window_open(session: Session, wa_contact_id: int, now: datetime | None = None) -> bool:
    """现在能不能发一般消息给这个号码（WhatsApp 24 小时规则）。"""
    ends = customer_service_window_ends_at(session, wa_contact_id)
    return ends is not None and (now or datetime.now(timezone.utc)) < ends


def _require_open(conversation: Conversation) -> None:
    if conversation.mode == ConversationMode.CLOSED:
        raise ConversationClosed("对话已结束")
