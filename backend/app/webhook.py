"""WhatsApp webhook（Phase 5）：Meta 把病人发来的消息、发出的消息的送达状态 POST 到这里。

- GET /webhook：在 Meta 设定 webhook 时，Meta 用 verify token 确认这是我们的服务器。
- POST /webhook：先检查签名（X-Hub-Signature-256），不是 Meta 送来的一律不处理。
- 同一条消息 Meta 可能送两次：record_incoming_message 用 wa_message_id 去重。
- 处理失败（例如数据库连不上）回 500，Meta 会再送一次；处理好了回 200。
- AI_REPLIES_ENABLED 没打开：新对话直接交给员工（D37）。打开了：回完 Meta 之后在背景让 AI 回复（app/ai_agent.py，D81）。
- 病人传的 IC / 护照号码：存之前先遮掉后面 6 位（D69，app/redact.py）。
"""

from __future__ import annotations

import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from . import ai_agent
from .config import WhatsAppSettings, ai_replies_enabled, get_whatsapp_settings
from .db import conversations as conv
from .db.models import ConversationMode
from .db.session import get_session
from .redact import mask_id_numbers
from .whatsapp import parse_webhook, valid_signature

log = logging.getLogger(__name__)

router = APIRouter(tags=["whatsapp webhook"])

AI_OFF_REASON = "AI replies are not turned on yet. Please reply to the patient."


async def _raw_body(request: Request) -> bytes:
    """签名是对"原封不动的 body"算的，所以要拿原始的 bytes，不能先转成 JSON。"""
    return await request.body()


@router.get("/webhook", response_class=PlainTextResponse)
def verify(
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
    settings: WhatsAppSettings = Depends(get_whatsapp_settings),
) -> str:
    if not settings.verify_token:
        raise HTTPException(status_code=503, detail="WHATSAPP_VERIFY_TOKEN is not set")
    if mode == "subscribe" and hmac.compare_digest(token.encode(), settings.verify_token.encode()):
        return challenge
    raise HTTPException(status_code=403, detail="Wrong verify token")


@router.post("/webhook")
def receive(
    background: BackgroundTasks,
    body: bytes = Depends(_raw_body),
    signature: str | None = Header(None, alias="X-Hub-Signature-256"),
    settings: WhatsAppSettings = Depends(get_whatsapp_settings),
    session: Session = Depends(get_session),
) -> dict:
    if not settings.app_secret or not settings.phone_number_id:
        raise HTTPException(status_code=503, detail="WhatsApp is not set up (WHATSAPP_APP_SECRET, WHATSAPP_PHONE_NUMBER_ID)")
    if not valid_signature(settings.app_secret, body, signature):
        log.warning("webhook 签名不对，不处理")
        raise HTTPException(status_code=401, detail="Bad signature")
    try:
        payload = json.loads(body)
    except ValueError:
        log.warning("webhook 不是 JSON，不处理")
        return {"received": 0}

    messages, statuses = parse_webhook(payload, settings.phone_number_id)
    new = 0
    ai_turns: set[int] = set()
    for m in messages:
        try:
            message, is_new = conv.record_incoming_message(
                session, m.wa_phone, mask_id_numbers(m.body), m.wa_message_id, profile_name=m.profile_name
            )
        except ValueError:
            log.warning("看不懂的号码，不处理这条消息（%s）", m.wa_message_id)
            continue
        if is_new:
            new += 1
            conversation = message.conversation
            if conversation.mode == ConversationMode.BOT:
                if ai_replies_enabled():
                    ai_turns.add(conversation.id)
                else:
                    conv.hand_over_to_human(session, conversation, AI_OFF_REASON)
    for s in statuses:
        conv.update_message_status(session, s.wa_message_id, s.status, s.error)
    session.commit()
    # AI 要几秒到几十秒：先回 Meta（不然它会再送一次），回完才跑。同一段对话的几条消息只跑一次
    for conversation_id in sorted(ai_turns):
        background.add_task(ai_agent.reply_in_background, conversation_id)
    log.info("webhook：%d 条新消息、%d 个送达状态", new, len(statuses))
    return {"received": len(messages) + len(statuses)}
