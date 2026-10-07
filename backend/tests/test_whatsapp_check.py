"""python -m app.whatsapp_check：一个假的 Meta（Graph API）+ 假的 tunnel，全部是假 ID、假 token。

tunnel 后面接的是真的 webhook 小程序（app/webhook_main.py），所以自我测试走的是真的签名检查。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, replace

import httpx
import pytest

from app.config import get_whatsapp_settings
from app.db.session import get_session
from app.whatsapp_check import Checker
from tests.test_whatsapp import NUMBER_ID, SETTINGS

APP_ID = "111111111111111"
WABA_ID = "222222222222222"
TUNNEL = "https://fake-words.trycloudflare.com/webhook"


@dataclass
class FakeMeta:
    """Meta 的设定，各个测试改其中一项。"""

    token_valid: bool = True
    debug_needs_app_token: bool = False                     # System User 的 token：不能用自己问 debug_token
    expires_at: int = 0                                     # 0 = 不会过期
    scopes: tuple[str, ...] = ("whatsapp_business_management", "whatsapp_business_messaging")
    messaging_wabas: tuple[str, ...] = ("333", WABA_ID)
    app_secret: str = SETTINGS.app_secret
    phone_number_ids: tuple[str, ...] = (NUMBER_ID,)
    waba_numbers: tuple[str, ...] | None = None              # WABA 里有哪些号码；None = phone_number_ids
    waba_apps: list[str] = field(default_factory=lambda: [APP_ID])
    callback_url: str | None = TUNNEL
    fields: tuple[str, ...] = ("messages",)
    tunnel_alive: bool = True
    requests: list[httpx.Request] = field(default_factory=list)

    def graph(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix(f"/{SETTINGS.api_version}/")
        token = request.headers["Authorization"].removeprefix("Bearer ")
        error = httpx.Response(400, json={"error": {"code": 100, "message": "Unsupported request"}})
        if path == "app" and token == SETTINGS.access_token:
            return httpx.Response(200, json={"id": APP_ID, "name": "Chatbot Test"})
        if path == "debug_token" and self.debug_needs_app_token and token != f"{APP_ID}|{self.app_secret}":
            return httpx.Response(400, json={"error": {"code": 100, "message": "(#100) You must provide an app access token"}})
        if path == "debug_token":
            return httpx.Response(200, json={"data": {
                "app_id": APP_ID, "is_valid": self.token_valid, "expires_at": self.expires_at,
                "scopes": list(self.scopes),
                "granular_scopes": [{"scope": "whatsapp_business_management", "target_ids": ["333", WABA_ID]},
                                    {"scope": "whatsapp_business_messaging", "target_ids": list(self.messaging_wabas)}],
            }})
        if path == f"{APP_ID}/subscriptions":
            if token != f"{APP_ID}|{self.app_secret}":
                return httpx.Response(400, json={"error": {"code": 190, "message": "Invalid OAuth access token"}})
            data = [] if self.callback_url is None else [{
                "object": "whatsapp_business_account", "callback_url": self.callback_url, "active": True,
                "fields": [{"name": f, "version": "v26.0"} for f in self.fields]}]
            return httpx.Response(200, json={"data": data})
        if token != SETTINGS.access_token:
            return httpx.Response(401, json={"error": {"code": 190, "message": "Invalid OAuth access token"}})
        if path in self.phone_number_ids:
            if request.url.params.get("fields") == "webhook_configuration":
                return httpx.Response(200, json={"webhook_configuration": {"application": self.callback_url}})
            return httpx.Response(200, json={"display_phone_number": "+1 555 010 4321", "verified_name": "Test Number"})
        if path == f"{WABA_ID}/phone_numbers":
            numbers = self.phone_number_ids if self.waba_numbers is None else self.waba_numbers
            return httpx.Response(200, json={"data": [{"id": n} for n in numbers]})
        if path == "333/phone_numbers":
            return httpx.Response(200, json={"data": [{"id": "999"}]})
        if path == f"{WABA_ID}/subscribed_apps":
            if request.method == "POST":
                self.waba_apps.append(APP_ID)
                return httpx.Response(200, json={"success": True})
            return httpx.Response(200, json={"data": [
                {"whatsapp_business_api_data": {"id": a, "name": f"App {a}"}} for a in self.waba_apps]})
        return error


@pytest.fixture
def check(session):
    """回传 run(meta, settings=SETTINGS, **kwargs) -> (problems, 印出来的文字)。"""
    from fastapi.testclient import TestClient

    from app.webhook_main import app

    def use_test_session():
        yield session

    app.dependency_overrides[get_session] = use_test_session
    window2 = TestClient(app)

    def run(meta: FakeMeta, settings=SETTINGS, window2_settings=SETTINGS, **kwargs):
        app.dependency_overrides[get_whatsapp_settings] = lambda: window2_settings

        def handler(request: httpx.Request) -> httpx.Response:
            meta.requests.append(request)
            if request.url.host == "graph.facebook.com":
                return meta.graph(request)
            if not meta.tunnel_alive:                       # cloudflared 重开过：旧网址
                return httpx.Response(530, text="error code: 1033")
            r = window2.request(request.method, request.url.path, params=request.url.params,
                                content=request.content, headers=dict(request.headers))
            return httpx.Response(r.status_code, content=r.content, headers=r.headers)

        lines: list[str] = []
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            problems = Checker(settings, http, out=lines.append).run(**kwargs)
        return problems, "\n".join(lines)

    yield run
    app.dependency_overrides.clear()


def test_everything_set_up(check, session):
    problems, text = check(FakeMeta())
    assert problems == []
    assert "App 已订阅 WABA" in text and "视窗 2 收下了" in text and "设定都对" in text
    assert TUNNEL in text
    # 可以贴到对话里：没有 token、secret；电话号码只有最后 4 位
    for secret in (SETTINGS.access_token, SETTINGS.app_secret, SETTINGS.verify_token):
        assert secret not in text
    assert "…4321" in text and "5550104321" not in text


def test_app_not_subscribed_to_waba(check):
    meta = FakeMeta(waba_apps=["444"])
    problems, text = check(meta)
    assert len(problems) == 1 and "--subscribe" in problems[0]
    assert "App 444" in text                               # 订阅了别的 App：印出名字
    assert not any(r.method == "POST" and "subscribed_apps" in r.url.path for r in meta.requests)

    problems, text = check(meta, subscribe=True)
    assert problems == []
    assert "刚刚订阅好了" in text and APP_ID in meta.waba_apps


def test_token_cannot_see_the_test_waba(check):
    """System user 加错了 WhatsApp 帐号：token 看得到的 WABA 里没有测试号码。"""
    problems, text = check(FakeMeta(waba_numbers=()))
    assert len(problems) == 1 and "Assign assets" in problems[0] and "--waba" in problems[0]
    assert f"333、{WABA_ID}" in text


def test_waba_given_by_hand(check):
    meta = FakeMeta()
    problems, _ = check(meta, waba_id=WABA_ID)
    assert problems == []
    assert not any("phone_numbers" in r.url.path for r in meta.requests)


def test_wrong_app_secret(check):
    problems, text = check(FakeMeta(app_secret="the-real-secret"))
    assert len(problems) == 1 and "WHATSAPP_APP_SECRET" in problems[0]
    assert "401" in text


def test_tunnel_url_changed(check):
    problems, text = check(FakeMeta(tunnel_alive=False))
    assert len(problems) == 1 and "Callback URL" in problems[0] and "视窗 3" in problems[0]
    assert "530" in text


def test_callback_url_without_webhook_path(check):
    problems, _ = check(FakeMeta(callback_url="https://fake-words.trycloudflare.com"))
    assert any("/webhook" in p for p in problems)


def test_messages_field_not_subscribed(check):
    problems, _ = check(FakeMeta(fields=("account_update",)))
    assert len(problems) == 1 and "messages" in problems[0]


def test_wrong_phone_number_id(check):
    problems, text = check(FakeMeta(phone_number_ids=("5555555555",)))
    assert len(problems) == 1 and "Phone number ID" in problems[0]
    assert "找不到测试号码在哪一个" not in text             # 不再多一个"找不到 WABA"让人混乱


def test_window2_not_restarted_after_env_change(check):
    old = replace(SETTINGS, app_secret="old-secret")
    problems, _ = check(FakeMeta(), window2_settings=old)
    assert len(problems) == 1 and "重开" in problems[0]

    problems, _ = check(FakeMeta(), window2_settings=replace(SETTINGS, phone_number_id="999"))
    assert len(problems) == 1 and "WHATSAPP_PHONE_NUMBER_ID" in problems[0]


def test_token_without_permission_to_send(check):
    problems, text = check(FakeMeta(scopes=("whatsapp_business_management",)))
    assert len(problems) == 1 and "重开视窗 1" in problems[0]
    assert "whatsapp_business_messaging" in text


def test_token_cannot_send_for_this_waba(check):
    problems, _ = check(FakeMeta(messaging_wabas=("333",)))
    assert len(problems) == 1 and "重开视窗 1" in problems[0]


def test_token_about_to_expire(check):
    problems, text = check(FakeMeta(expires_at=int(time.time()) + 600))
    assert len(problems) == 1 and "System User" in problems[0]
    assert "分钟后就失效" in text

    problems, text = check(FakeMeta(expires_at=int(time.time()) + 5 * 3600 + 60))
    assert problems == [] and "大约 5 小时后失效" in text

    problems, text = check(FakeMeta(expires_at=int(time.time()) + 60 * 86400))
    assert problems == [] and "大约 59 天后失效" in text


def test_system_user_token(check):
    """System User 的 token 不能自己问 debug_token：改用 App 的身份问，结果一样。"""
    problems, text = check(FakeMeta(debug_needs_app_token=True))
    assert problems == [] and "access token 有效" in text

    problems, text = check(FakeMeta(debug_needs_app_token=True, app_secret="the-real-secret"))
    assert len(problems) == 1 and "access token 不能用" in text and "#100" in text


def test_expired_token_stops_early(check):
    meta = FakeMeta(token_valid=False)
    problems, _ = check(meta)
    assert len(problems) == 1 and "System User" in problems[0]
    assert len(meta.requests) == 1


def test_env_not_filled_in(check):
    meta = FakeMeta()
    problems, text = check(meta, settings=replace(SETTINGS, app_secret="CHANGE_ME", phone_number_id=""))
    assert len(problems) == 1
    assert "WHATSAPP_APP_SECRET" in text and "WHATSAPP_PHONE_NUMBER_ID" in text
    assert meta.requests == []


def test_self_test_saves_nothing(check, session):
    from sqlalchemy import func, select

    from app.db.models import Message

    before = session.scalar(select(func.count()).select_from(Message))
    meta = FakeMeta()
    check(meta)
    assert session.scalar(select(func.count()).select_from(Message)) == before
    posted = [r for r in meta.requests if r.method == "POST" and r.url.host != "graph.facebook.com"]
    assert len(posted) == 1 and json.loads(posted[0].content)["entry"][0]["changes"][0]["value"]["statuses"]
