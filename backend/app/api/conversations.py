"""对话：看列表、看完整对话、接手、交回 AI、结束、回复病人（docs/architecture.md 第 5 节）。

回复病人（Phase 5）：经 WhatsApp Cloud API 真的发出去，再存进 messages；送达状态由 webhook 更新。
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_staff
from ..db import conversations as conv
from ..db.models import Conversation, ConversationMode, Message, Sender, Staff, WaStatus
from ..db.session import get_session
from ..whatsapp import MAX_TEXT_LENGTH, RecipientNotAllowed, WhatsAppClient, WhatsAppError, WhatsAppNotConfigured, \
    get_whatsapp_client

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"], dependencies=[Depends(current_staff)])

PREVIEW_LENGTH = 100


class MessageOut(BaseModel):
    id: int
    sender: Sender
    staff_id: int | None
    body: str
    wa_status: WaStatus | None
    wa_error: str | None
    created_at: datetime


class ConversationOut(BaseModel):
    id: int
    wa_phone: str
    profile_name: str | None
    mode: ConversationMode
    assigned_staff_id: int | None
    assigned_staff_name: str | None
    handover_reason: str | None
    created_at: datetime
    closed_at: datetime | None
    last_message_at: datetime | None
    last_message_sender: Sender | None
    last_message_preview: str | None


class ConversationDetailOut(ConversationOut):
    # WhatsApp 24 小时规则：到这个时间之前才能回复一般消息（病人最后一条消息 + 24 小时）；没收过消息 = null
    reply_window_ends_at: datetime | None
    messages: list[MessageOut]


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)


def _out(c: Conversation, last: Message | None) -> dict:
    return dict(
        id=c.id,
        wa_phone=c.wa_contact.wa_phone,
        profile_name=c.wa_contact.profile_name,
        mode=c.mode,
        assigned_staff_id=c.assigned_staff_id,
        assigned_staff_name=c.assigned_staff.name if c.assigned_staff else None,
        handover_reason=c.handover_reason,
        created_at=c.created_at,
        closed_at=c.closed_at,
        last_message_at=last.created_at if last else None,
        last_message_sender=last.sender if last else None,
        last_message_preview=last.body[:PREVIEW_LENGTH] if last else None,
    )


def _get(session: Session, conversation_id: int) -> Conversation:
    c = session.get(Conversation, conversation_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return c


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    mode: ConversationMode | None = Query(None, description="不填 = 没结束的（BOT + HUMAN）"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> list[dict]:
    """最近有消息的排前面。"""
    last_id = (
        select(Message.conversation_id, func.max(Message.id).label("message_id"))
        .group_by(Message.conversation_id)
        .subquery()
    )
    stmt = (
        select(Conversation, Message)
        .outerjoin(last_id, last_id.c.conversation_id == Conversation.id)
        .outerjoin(Message, Message.id == last_id.c.message_id)
        .options(selectinload(Conversation.wa_contact), selectinload(Conversation.assigned_staff))
        .order_by(func.coalesce(Message.created_at, Conversation.created_at).desc(), Conversation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if mode is None:
        stmt = stmt.where(Conversation.mode != ConversationMode.CLOSED)
    else:
        stmt = stmt.where(Conversation.mode == mode)
    return [_out(c, last) for c, last in session.execute(stmt)]


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(conversation_id: int, session: Session = Depends(get_session)) -> dict:
    c = _get(session, conversation_id)
    messages = c.messages
    return {**_out(c, messages[-1] if messages else None),
            "reply_window_ends_at": conv.customer_service_window_ends_at(session, c.wa_contact_id),
            "messages": [MessageOut.model_validate(m, from_attributes=True) for m in messages]}


def _act(session: Session, conversation_id: int, action) -> dict:
    c = _get(session, conversation_id)
    try:
        action(c)
    except conv.ConversationClosed as e:
        raise HTTPException(status_code=409, detail="This conversation is already closed") from e
    session.commit()
    return get_conversation(conversation_id, session)


@router.post("/{conversation_id}/take-over", response_model=ConversationDetailOut)
def take_over(
    conversation_id: int, staff: Staff = Depends(current_staff), session: Session = Depends(get_session)
) -> dict:
    """员工接手：AI 停止回复这段对话。"""
    return _act(session, conversation_id, lambda c: conv.take_over(session, c, staff))


@router.post("/{conversation_id}/hand-back", response_model=ConversationDetailOut)
def hand_back(conversation_id: int, session: Session = Depends(get_session)) -> dict:
    """交回 AI 继续回复。"""
    return _act(session, conversation_id, lambda c: conv.hand_back_to_bot(session, c))


@router.post("/{conversation_id}/close", response_model=ConversationDetailOut)
def close(conversation_id: int, session: Session = Depends(get_session)) -> dict:
    """结束对话。病人之后再发消息会开一段新的对话。"""
    return _act(session, conversation_id, lambda c: conv.close_conversation(session, c))


@router.post("/{conversation_id}/reply", response_model=ConversationDetailOut)
def reply(
    conversation_id: int,
    body: ReplyIn,
    staff: Staff = Depends(current_staff),
    session: Session = Depends(get_session),
    whatsapp: WhatsAppClient = Depends(get_whatsapp_client),
) -> dict:
    """员工回复病人。在 AI 回复的对话里回复 = 接手（D22）。

    先发出去，WhatsApp 收下了才存进数据库：存进去的消息一定是真的发出去了（D36）。
    """
    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=422, detail="The message is empty")
    c = _get(session, conversation_id)
    if c.mode == ConversationMode.CLOSED:
        raise HTTPException(status_code=409, detail="This conversation is already closed")
    if not conv.customer_service_window_open(session, c.wa_contact_id):
        raise HTTPException(
            status_code=409,
            detail="More than 24 hours since the patient's last message. WhatsApp only allows approved "
                   "template messages now, which are not available yet.",
        )
    try:
        wa_message_id = whatsapp.send_text(c.wa_contact.wa_phone, text)
    except RecipientNotAllowed as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except WhatsAppNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except WhatsAppError as e:
        raise HTTPException(status_code=502, detail=f"WhatsApp did not accept the message: {e}") from e

    try:
        conv.record_outgoing_message(session, c, Sender.STAFF, text, staff=staff,
                                     wa_message_id=wa_message_id, wa_status=WaStatus.ACCEPTED)
        session.commit()
    except Exception:
        # 病人已经收到了，但记录没存进去：留下消息 ID，方便查
        log.exception("消息已经发出，但存进数据库失败（%s）", wa_message_id)
        raise
    return get_conversation(conversation_id, session)
