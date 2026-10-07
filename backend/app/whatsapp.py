"""WhatsApp Cloud API（Phase 5）：看懂 Meta 送来的 webhook、检查签名、发文字消息。

- 设置在 backend/.env（见 .env.example）。access token、app secret 绝不写进仓库，也不写进日志。
- 开发时只用 Meta 的测试号码，而且只发给 WHATSAPP_ALLOWED_RECIPIENTS 里的号码（D34）：
  就算程序有 bug，也不会发给真的病人。
- 日志不记消息内容和电话号码（病人资料），只记数量和消息 ID。
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from functools import lru_cache

import httpx

from .config import WhatsAppSettings, get_whatsapp_settings
from .db.models import WaStatus
from .phone import normalize_phone

log = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com"
MAX_TEXT_LENGTH = 4096          # WhatsApp 一条文字消息最长 4096 个字
TOKEN_HINT = "Check WHATSAPP_ACCESS_TOKEN on the server: renew it, then restart the Admin API."


class WhatsAppError(Exception):
    """WhatsApp 不接受这条消息，或连不上。信息是给员工看的（不含 token）。"""


class WhatsAppNotConfigured(WhatsAppError):
    pass


class RecipientNotAllowed(WhatsAppError):
    pass


# ---------- 收：webhook ----------

def valid_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    """Meta 用 App Secret 对整个 request body 算 HMAC-SHA256，放在 X-Hub-Signature-256。

    签名不对 = 不是 Meta 送来的（任何人都可以 POST 到我们的网址），一律不处理。
    """
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    # 用 bytes 比较：header 里有奇怪的字（非 ASCII）也不会出错
    return hmac.compare_digest(expected.encode(), header.removeprefix("sha256=").encode())


@dataclass(frozen=True)
class IncomingMessage:
    wa_message_id: str
    wa_phone: str
    profile_name: str | None
    body: str


@dataclass(frozen=True)
class StatusUpdate:
    wa_message_id: str
    status: WaStatus
    error: str | None


# 还不支持的消息种类：先存一个说明，员工到诊所的手机上看（D38：不下载照片、语音，病人资料）
_MEDIA = {"image": "Image", "video": "Video", "audio": "Voice message", "document": "Document", "sticker": "Sticker"}

_STATUSES = {"sent": WaStatus.SENT, "delivered": WaStatus.DELIVERED, "read": WaStatus.READ, "failed": WaStatus.FAILED}


def _message_body(m: dict) -> str:
    kind = m.get("type")
    if kind == "text":
        return (m.get("text") or {}).get("body") or ""
    if kind in _MEDIA:
        caption = (m.get(kind) or {}).get("caption")
        return f"[{_MEDIA[kind]}]" + (f" {caption}" if caption else "")
    if kind == "button":                                    # 病人按了模板消息上的按钮
        return (m.get("button") or {}).get("text") or "[Button]"
    if kind == "interactive":
        i = m.get("interactive") or {}
        reply = i.get("button_reply") or i.get("list_reply") or {}
        return reply.get("title") or "[Reply]"
    if kind == "location":
        return "[Location]"
    if kind == "contacts":
        return "[Contact card]"
    if kind == "reaction":
        emoji = (m.get("reaction") or {}).get("emoji")
        return f"[Reaction {emoji}]" if emoji else "[Reaction removed]"
    return "[Message type not supported yet]"


def _error_text(errors: list | None) -> str | None:
    """status = failed 的原因，例 "131047: Re-engagement message – More than 24 hours have passed …" """
    if not errors:
        return None
    e = errors[0] or {}
    details = (e.get("error_data") or {}).get("details")
    text = f"{e.get('code', '?')}: {e.get('title') or e.get('message') or 'Unknown error'}"
    return f"{text} – {details}" if details and details != e.get("title") else text


def parse_webhook(payload: dict, phone_number_id: str) -> tuple[list[IncomingMessage], list[StatusUpdate]]:
    """从 webhook 里拿出病人发来的消息、发出的消息的送达状态。

    只看发给我们这个号码（phone_number_id）的；其他种类的通知（例如帐号设定改了）不管。
    """
    messages: list[IncomingMessage] = []
    statuses: list[StatusUpdate] = []
    if payload.get("object") != "whatsapp_business_account":
        return messages, statuses
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            if change.get("field") != "messages":
                continue
            other = (value.get("metadata") or {}).get("phone_number_id")
            if other != phone_number_id:
                # 常见原因：.env 的 WHATSAPP_PHONE_NUMBER_ID 填错（填成电话号码或 WABA ID）。号码 ID 不是病人资料
                log.warning("webhook 是给另一个号码 ID（%s）的，不处理：检查 .env 的 WHATSAPP_PHONE_NUMBER_ID", other)
                continue
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts") or []}
            for m in value.get("messages") or []:
                if m.get("id") and m.get("from"):
                    messages.append(IncomingMessage(
                        wa_message_id=m["id"], wa_phone=m["from"], profile_name=names.get(m["from"]),
                        body=_message_body(m),
                    ))
            for s in value.get("statuses") or []:
                status = _STATUSES.get(s.get("status"))
                if status and s.get("id"):
                    statuses.append(StatusUpdate(s["id"], status, _error_text(s.get("errors"))))
    return messages, statuses


# ---------- 发：Cloud API ----------

class WhatsAppClient:
    def __init__(self, settings: WhatsAppSettings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self._http = httpx.Client(base_url=GRAPH_URL, transport=transport, timeout=15)

    def send_text(self, to: str, body: str) -> str:
        """发一条文字消息，回传 WhatsApp 的消息 ID（wamid）。WhatsApp 不接受就 raise WhatsAppError。

        WhatsApp 收下了不代表病人收到：之后的 status webhook 才知道（update_message_status）。
        """
        s = self.settings
        if not s.access_token or not s.phone_number_id:
            raise WhatsAppNotConfigured(
                "WhatsApp is not set up on the server (WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID)"
            )
        phone = normalize_phone(to)
        if phone is None or not s.can_send_to(phone):
            raise RecipientNotAllowed(
                "This number is not in WHATSAPP_ALLOWED_RECIPIENTS. During development, messages can only "
                "be sent to your own test numbers."
            )
        try:
            r = self._http.post(
                f"/{s.api_version}/{s.phone_number_id}/messages",
                headers={"Authorization": f"Bearer {s.access_token}"},
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": phone,
                    "type": "text",
                    "text": {"preview_url": False, "body": body},
                },
            )
        except httpx.HTTPError as e:
            log.warning("连不上 WhatsApp：%s", type(e).__name__)
            raise WhatsAppError("Cannot reach WhatsApp. Please try again.") from None

        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code != 200:
            error = data.get("error") or {}
            details = (error.get("error_data") or {}).get("details")
            code = error.get("code")
            log.warning("WhatsApp 不接受消息：HTTP %s，code %s", r.status_code, code)
            text = details or error.get("message") or f"HTTP {r.status_code}"
            if code is not None:
                text += f" (code {code})"
            if _token_problem(code):
                text += f" {TOKEN_HINT}"
            raise WhatsAppError(text)
        try:
            return data["messages"][0]["id"]
        except (KeyError, IndexError, TypeError):
            raise WhatsAppError("WhatsApp did not return a message ID") from None


def _token_problem(code) -> bool:
    """Meta 的错误代码：0 / 190 = token 不对或过期；3、10、200–299 = token 没有权限（例如没有 whatsapp_business_messaging）。"""
    return isinstance(code, int) and (code in (0, 3, 10, 190) or 200 <= code <= 299)


@lru_cache
def _default_client() -> WhatsAppClient:
    return WhatsAppClient(get_whatsapp_settings())


def get_whatsapp_client() -> WhatsAppClient:
    """FastAPI dependency。设置在启动时读一次：改了 .env 要重新启动 uvicorn。"""
    return _default_client()
