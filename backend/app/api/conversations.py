"""对话：看列表、看完整对话、接手、交回 AI、结束（docs/architecture.md 第 5 节）。

员工回复病人要等 Phase 5 接上 WhatsApp 才做：现在存一条"发出"的消息，病人其实收不到，会误导员工。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_staff
from ..db import conversations as conv
from ..db.models import Conversation, ConversationMode, Message, Sender, Staff
from ..db.session import get_session

router = APIRouter(prefix="/api/conversations", tags=["conversations"], dependencies=[Depends(current_staff)])

PREVIEW_LENGTH = 100


class MessageOut(BaseModel):
    id: int
    sender: Sender
    staff_id: int | None
    body: str
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
    messages: list[MessageOut]


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
