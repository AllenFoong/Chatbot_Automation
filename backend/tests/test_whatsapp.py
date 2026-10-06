"""WhatsApp Cloud API（Phase 5）：webhook、签名、发消息。全部是假号码、假消息、假的 token。

不连 Meta：webhook 用自己签名的假 payload，发消息用 httpx 的 MockTransport。
"""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest
from sqlalchemy import func, select

from app.config import WhatsAppSettings, get_whatsapp_settings
from app.db import conversations as conv
from app.db.models import ConversationMode, Message, Sender, WaStatus
from app.db.session import get_session
from app.webhook import AI_OFF_REASON
from app.whatsapp import (RecipientNotAllowed, WhatsAppClient, WhatsAppError, WhatsAppNotConfigured,
                          parse_webhook, valid_signature)
from tests.database import add_staff

PHONE = "60123456789"
NUMBER_ID = "1234567890"
SETTINGS = WhatsAppSettings(
    verify_token="test-verify-token", app_secret="test-app-secret", access_token="test-access-token",
    phone_number_id=NUMBER_ID, api_version="v26.0", allowed_recipients=frozenset({PHONE}),
)


def payload(messages=(), statuses=(), phone_number_id=NUMBER_ID, name="Test Patient"):
    value = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "15550000000", "phone_number_id": phone_number_id},
        "contacts": [{"profile": {"name": name}, "wa_id": PHONE}],
        "messages": list(messages),
        "statuses": list(statuses),
    }
    return {"object": "whatsapp_business_account",
            "entry": [{"id": "0", "changes": [{"field": "messages", "value": value}]}]}


def text(wamid, body="Hi, can I book scaling?"):
    return {"from": PHONE, "id": wamid, "timestamp": "1791000000", "type": "text", "text": {"body": body}}


def status(wamid, state, errors=None):
    s = {"id": wamid, "status": state, "timestamp": "1791000000", "recipient_id": PHONE}
    if errors:
        s["errors"] = errors
    return s


def sign(body: bytes, secret=SETTINGS.app_secret) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def webhook(session):
    from fastapi.testclient import TestClient

    from app.webhook_main import app

    def use_test_session():
        yield session

    app.dependency_overrides[get_session] = use_test_session
    app.dependency_overrides[get_whatsapp_settings] = lambda: SETTINGS

    def post(data, signature=None):
        body = json.dumps(data).encode()
        return client.post("/webhook", content=body, headers={
            "Content-Type": "application/json", "X-Hub-Signature-256": signature or sign(body)})

    client = TestClient(app)
    client.post_signed = post
    yield client
    app.dependency_overrides.clear()


def count_messages(session) -> int:
    return session.scalar(select(func.count()).select_from(Message))


# ---------- 设定 ----------

def test_allowed_recipients_from_env(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ALLOWED_RECIPIENTS", "012-345 6789, +65 9123 4567, nonsense")
    assert get_whatsapp_settings().allowed_recipients == {"60123456789", "6591234567"}
    monkeypatch.setenv("WHATSAPP_ALLOWED_RECIPIENTS", "")
    assert get_whatsapp_settings().allowed_recipients == frozenset()        # 没设定 = 谁都不能发
    monkeypatch.setenv("WHATSAPP_ALLOWED_RECIPIENTS", "*")
    assert get_whatsapp_settings().can_send_to("60199999999")               # 只有上线才这样设


# ---------- 签名、解读 webhook ----------

def test_signature():
    body = b'{"a": 1}'
    assert valid_signature("secret", body, sign(body, "secret"))
    assert not valid_signature("secret", body, sign(body, "other"))
    assert not valid_signature("secret", body + b" ", sign(body, "secret"))     # body 被改过
    assert not valid_signature("secret", body, None)
    assert not valid_signature("", body, sign(body, ""))                        # 没设定 secret：一律拒绝
    assert not valid_signature("secret", body, "sha256=签名")                   # 奇怪的字：拒绝，不会出错


def test_parse_message_types():
    msgs = [
        text("w1", "Hello"),
        {"from": PHONE, "id": "w2", "type": "image", "image": {"caption": "my tooth", "id": "media1"}},
        {"from": PHONE, "id": "w3", "type": "audio", "audio": {"id": "media2"}},
        {"from": PHONE, "id": "w4", "type": "interactive", "interactive": {"button_reply": {"title": "Yes"}}},
        {"from": PHONE, "id": "w5", "type": "reaction", "reaction": {"emoji": "👍", "message_id": "x"}},
        {"from": PHONE, "id": "w6", "type": "something_new"},
    ]
    messages, _ = parse_webhook(payload(msgs), NUMBER_ID)
    assert [m.body for m in messages] == [
        "Hello", "[Image] my tooth", "[Voice message]", "Yes", "[Reaction 👍]", "[Message type not supported yet]"]
    assert messages[0].profile_name == "Test Patient" and messages[0].wa_phone == PHONE


def test_parse_statuses_with_error():
    _, statuses = parse_webhook(payload(statuses=[
        status("w1", "delivered"),
        status("w2", "failed", [{"code": 131047, "title": "Re-engagement message",
                                 "error_data": {"details": "More than 24 hours have passed"}}]),
        status("w3", "deleted"),                       # 不认识的状态：不管
    ]), NUMBER_ID)
    assert [(s.wa_message_id, s.status) for s in statuses] == [("w1", WaStatus.DELIVERED), ("w2", WaStatus.FAILED)]
    assert statuses[1].error == "131047: Re-engagement message – More than 24 hours have passed"


def test_parse_ignores_other_numbers_and_other_notifications():
    assert parse_webhook(payload([text("w1")], phone_number_id="999"), NUMBER_ID) == ([], [])
    assert parse_webhook({"object": "page", "entry": []}, NUMBER_ID) == ([], [])
    other_field = payload([text("w1")])
    other_field["entry"][0]["changes"][0]["field"] = "account_update"
    assert parse_webhook(other_field, NUMBER_ID) == ([], [])


# ---------- webhook（连测试数据库） ----------

def test_webhook_verification(webhook):
    ok = webhook.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "test-verify-token",
                                         "hub.challenge": "12345"})
    assert ok.status_code == 200 and ok.text == "12345"
    wrong = webhook.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "guess",
                                            "hub.challenge": "12345"})
    assert wrong.status_code == 403
    odd = webhook.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "令牌",
                                          "hub.challenge": "12345"})
    assert odd.status_code == 403


def test_webhook_rejects_bad_signature(webhook, session):
    r = webhook.post_signed(payload([text("w1")]), signature="sha256=" + "0" * 64)
    assert r.status_code == 401
    r = webhook.post("/webhook", json=payload([text("w1")]))           # 没有签名
    assert r.status_code == 401
    assert count_messages(session) == 0


def test_new_message_goes_to_staff_while_ai_is_off(webhook, session):
    r = webhook.post_signed(payload([text("w1")]))
    assert r.status_code == 200
    msg = session.scalars(select(Message)).one()
    assert (msg.sender, msg.body, msg.wa_message_id) == (Sender.CUSTOMER, "Hi, can I book scaling?", "w1")
    assert msg.conversation.wa_contact.profile_name == "Test Patient"
    assert msg.conversation.mode == ConversationMode.HUMAN                 # 还没有 AI：交给员工（D37）
    assert msg.conversation.handover_reason == AI_OFF_REASON


def test_new_message_stays_with_ai_when_ai_is_on(webhook, session, monkeypatch):
    monkeypatch.setenv("AI_REPLIES_ENABLED", "true")
    webhook.post_signed(payload([text("w1")]))
    assert session.scalars(select(Message)).one().conversation.mode == ConversationMode.BOT


def test_same_message_twice_is_saved_once(webhook, session):
    webhook.post_signed(payload([text("w1")]))
    webhook.post_signed(payload([text("w1")]))                             # Meta 重送
    assert count_messages(session) == 1


def test_message_for_another_number_is_ignored(webhook, session):
    r = webhook.post_signed(payload([text("w1")], phone_number_id="999"))
    assert r.status_code == 200 and count_messages(session) == 0


def test_delivery_status_updates_the_staff_reply(webhook, session):
    first, _ = conv.record_incoming_message(session, PHONE, "Hi", "w-in")
    reply = conv.record_outgoing_message(session, first.conversation, Sender.STAFF, "Hello!",
                                         staff=add_staff(session), wa_message_id="w-out",
                                         wa_status=WaStatus.ACCEPTED)
    webhook.post_signed(payload(statuses=[status("w-out", "read"), status("w-out", "delivered")]))
    assert reply.wa_status == WaStatus.READ
    webhook.post_signed(payload(statuses=[status("w-out", "failed", [{"code": 131026, "title": "Undeliverable"}])]))
    assert (reply.wa_status, reply.wa_error) == (WaStatus.FAILED, "131026: Undeliverable")


def test_webhook_app_only_has_the_webhook(webhook):
    """放到网上的只有 /webhook：Admin API、空档、API 文件都不在这个程序里（D35）。"""
    for path in ("/api/conversations", "/api/auth/me", "/availability", "/docs", "/openapi.json"):
        assert webhook.get(path).status_code == 404, path
    assert webhook.get("/health").json() == {"status": "ok"}


def test_webhook_refuses_when_not_set_up(webhook):
    from app.webhook_main import app

    app.dependency_overrides[get_whatsapp_settings] = lambda: WhatsAppSettings("", "", "", "", "v26.0", frozenset())
    assert webhook.post_signed(payload([text("w1")])).status_code == 503
    assert webhook.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "",
                                           "hub.challenge": "1"}).status_code == 503


# ---------- 发消息（不连 Meta：MockTransport） ----------

def client_with(handler, settings=SETTINGS) -> tuple[WhatsAppClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    return WhatsAppClient(settings, transport=httpx.MockTransport(record)), requests


def test_send_text():
    client, requests = client_with(lambda r: httpx.Response(200, json={
        "messaging_product": "whatsapp", "contacts": [{"input": PHONE, "wa_id": PHONE}],
        "messages": [{"id": "wamid.ABC"}]}))
    assert client.send_text("+60 12-345 6789", "Hello!") == "wamid.ABC"
    r = requests[0]
    assert str(r.url) == f"https://graph.facebook.com/v26.0/{NUMBER_ID}/messages"
    assert r.headers["Authorization"] == "Bearer test-access-token"
    assert json.loads(r.content) == {"messaging_product": "whatsapp", "recipient_type": "individual", "to": PHONE,
                                     "type": "text", "text": {"preview_url": False, "body": "Hello!"}}


def test_send_only_to_allowed_numbers():
    client, requests = client_with(lambda r: httpx.Response(200, json={"messages": [{"id": "x"}]}))
    with pytest.raises(RecipientNotAllowed):
        client.send_text("60199999999", "Hello!")
    assert requests == []                                   # 根本没有发出去


def test_send_error_explains_without_token():
    client, _ = client_with(lambda r: httpx.Response(400, json={"error": {
        "message": "(#131030) Recipient phone number not in allowed list", "code": 131030,
        "error_data": {"details": "Recipient phone number not in allowed list: Add recipient phone number"}}}))
    with pytest.raises(WhatsAppError) as e:
        client.send_text(PHONE, "Hello!")
    assert "not in allowed list" in str(e.value) and "test-access-token" not in str(e.value)


def test_send_when_whatsapp_unreachable():
    def down(request):
        raise httpx.ConnectError("no network")

    client, _ = client_with(down)
    with pytest.raises(WhatsAppError, match="Cannot reach WhatsApp"):
        client.send_text(PHONE, "Hello!")


def test_send_when_not_set_up():
    client, _ = client_with(lambda r: httpx.Response(200), WhatsAppSettings("", "", "", "", "v26.0", None))
    with pytest.raises(WhatsAppNotConfigured):
        client.send_text(PHONE, "Hello!")
