"""检查 WhatsApp 的设定（Phase 5a）：手机传给测试号码的消息，为什么没有送到 webhook。

用法（在 backend/ 里，先启用 venv；视窗 2、3 要开着）：
    python -m app.whatsapp_check                 只检查，不改任何东西
    python -m app.whatsapp_check --subscribe     App 没订阅测试的 WABA 的话，帮你订阅（= README 第 9 步）
    python -m app.whatsapp_check --waba <ID>     找不到 WABA 时，填 API Setup 上的 WhatsApp Business Account ID

逐项问 Meta（Graph API），再经 tunnel 打一次自己的 webhook：
1. .env 的 4 个值都填了
2. access token 有效，是哪一个 App 的
   有没有发消息的权限（whatsapp_business_messaging）、是不是快过期了
3. WHATSAPP_PHONE_NUMBER_ID 真的是测试号码的 ID；Meta 把这个号码的 webhook 送到哪个网址
4. App 有没有订阅测试号码所在的 WhatsApp Business Account（WABA）：没有 = 手机的消息不会送来
5. App secret 对不对；App 的 webhook 有没有订阅 messages
6. Meta 用的网址现在连得到视窗 2 吗（cloudflared 重开过，网址就变了）
7. 经这个网址送一个签了名的假 webhook：只有一个找不到的送达状态，数据库不会多任何东西

印出来的东西没有 token、secret；电话号码只留最后 4 位：可以贴到对话里。
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import secrets
import sys
import time
from collections.abc import Callable

import httpx

from .config import WhatsAppSettings, get_whatsapp_settings
from .whatsapp import GRAPH_URL


class GraphError(Exception):
    pass


# 换 token 的方法（README「Phase 5a」的 System User token：60 天；API Setup 按出来的 token 大约 1 小时就失效）
RENEW = "照 README「Phase 5a」的「System User 的 access token」换一个新的 token，更新 .env 的 WHATSAPP_ACCESS_TOKEN，再重开视窗 1"


class Checker:
    def __init__(self, settings: WhatsAppSettings, http: httpx.Client, out: Callable[[str], None] = print):
        self.s = settings
        self.http = http
        self.out = out
        self.problems: list[str] = []
        self.messaging_wabas: list[str] | None = None     # token 能发消息的 WABA；None = 没有列出来（= 全部）

    # ---------- 印出结果 ----------

    def ok(self, text: str) -> None:
        self.out(f"[OK] {text}")

    def bad(self, text: str, fix: str) -> None:
        self.out(f"[!!] {text}\n     → {fix}")
        self.problems.append(fix)

    def info(self, text: str) -> None:
        self.out(f"     {text}")

    def _clean(self, text: str) -> str:
        """Meta 的错误信息不会带 token；保险起见，万一有也换掉。"""
        for secret in (self.s.access_token, self.s.app_secret, self.s.verify_token):
            if secret:
                text = text.replace(secret, "***")
        return text

    # ---------- Graph API ----------

    def graph(self, path: str, token: str | None = None, method: str = "GET", params: dict | None = None) -> dict:
        try:
            r = self.http.request(
                method, f"{GRAPH_URL}/{self.s.api_version}/{path}", params=params,
                headers={"Authorization": f"Bearer {token or self.s.access_token}"},
            )
        except httpx.HTTPError as e:
            raise GraphError(f"连不上 Meta（{type(e).__name__}）") from None
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code != 200 or "error" in data:
            error = data.get("error") or {}
            raise GraphError(self._clean(f"{error.get('code', r.status_code)}: {error.get('message', 'HTTP error')}"))
        return data

    # ---------- 检查 ----------

    def run(self, waba_id: str | None = None, subscribe: bool = False) -> list[str]:
        self.out("WhatsApp 设定检查（不会印出 token、secret）")
        if not self.check_env():
            return self.problems
        app_id, waba_candidates = self.check_token()
        if app_id is None:
            return self.problems
        webhook_config = self.check_phone_number()
        waba_override = None
        if webhook_config is not None or waba_id:       # 号码 ID 不对，就找不到它在哪个 WABA
            waba_override = self.check_waba(app_id, waba_id or None, waba_candidates, subscribe)
        app_callback = self.check_app_webhook(app_id)
        url = self.effective_url(webhook_config or {}, waba_override, app_callback)
        if url and self.check_url(url):
            self.check_self_test(url)
        self.out("")
        if self.problems:
            self.out("要处理的（照顺序做，做完再跑一次这个检查）：")
            for i, fix in enumerate(self.problems, 1):
                self.out(f"  {i}. {fix}")
        else:
            self.out("设定都对。手机再传一条消息给测试号码：视窗 2 应该出现 POST /webhook 200 和「1 条新消息」。")
            self.out("还是没有的话，把这次的输出和视窗 2 的最后几行贴到对话里。")
        return self.problems

    def check_env(self) -> bool:
        values = {
            "WHATSAPP_VERIFY_TOKEN": self.s.verify_token, "WHATSAPP_APP_SECRET": self.s.app_secret,
            "WHATSAPP_ACCESS_TOKEN": self.s.access_token, "WHATSAPP_PHONE_NUMBER_ID": self.s.phone_number_id,
        }
        missing = [name for name, value in values.items() if not value or value == "CHANGE_ME"]
        if missing:
            self.bad(f".env 还没填：{', '.join(missing)}", "照 README「Phase 5a」第 5 步填好 backend\\.env")
            return False
        self.ok(".env：4 个值都填了")
        return True

    def debug_token(self) -> dict:
        """问 Meta 这个 token 是哪个 App 的、权限、什么时候失效。

        先用 token 自己问；不行的话（例如 System User 的 token），用 App 自己的身份（App ID|App secret）再问一次。
        """
        params = {"input_token": self.s.access_token}
        try:
            return self.graph("debug_token", params=params)["data"]
        except GraphError as first:
            try:
                app_id = self.graph("app")["id"]
                return self.graph("debug_token", token=f"{app_id}|{self.s.app_secret}", params=params)["data"]
            except (GraphError, KeyError, TypeError):
                raise first from None

    def check_token(self) -> tuple[str | None, list[str]]:
        try:
            data = self.debug_token()
        except (GraphError, KeyError, TypeError) as e:
            self.bad(f"access token 不能用（{e}）", RENEW)
            return None, []
        if not data.get("is_valid"):
            self.bad("access token 已经失效", RENEW)
            return None, []
        expires = data.get("expires_at") or 0
        seconds_left = int(expires - time.time()) if expires else None
        if seconds_left is not None and seconds_left < 3600:
            self.bad(f"access token 有效，但 {max(0, seconds_left) // 60} 分钟后就失效（App ID {data.get('app_id')}）", RENEW)
        else:
            hours = seconds_left // 3600 if seconds_left is not None else None
            left = "" if hours is None else f"，大约 {hours // 24} 天后失效" if hours >= 48 else f"，大约 {hours} 小时后失效"
            self.ok(f"access token 有效（App ID {data.get('app_id')}{left}）")
        scopes = data.get("scopes")
        if isinstance(scopes, list) and "whatsapp_business_messaging" not in scopes:
            self.bad("access token 没有发消息的权限（whatsapp_business_messaging）：Admin Platform 回复会被拒绝",
                     "产生 token 时要勾 whatsapp_business_messaging 和 whatsapp_business_management。" + RENEW)
        self.info("发消息的是视窗 1：它只在启动时读 .env。换了 token 一定要重开视窗 1，不然回复会显示 access token 的错误")
        wabas: list[str] = []
        for scope in data.get("granular_scopes") or []:
            if scope.get("scope") in ("whatsapp_business_management", "whatsapp_business_messaging"):
                wabas += [w for w in scope.get("target_ids") or [] if w not in wabas]
            if scope.get("scope") == "whatsapp_business_messaging" and scope.get("target_ids"):
                self.messaging_wabas = list(scope["target_ids"])
        return data.get("app_id"), wabas

    def check_phone_number(self) -> dict | None:
        """回传 Meta 对这个号码的 webhook 设定（问不到 = {}）；号码 ID 不对回传 None。"""
        try:
            info = self.graph(self.s.phone_number_id, params={"fields": "display_phone_number,verified_name"})
        except GraphError as e:
            self.bad(f"WHATSAPP_PHONE_NUMBER_ID 找不到（{e}）",
                     "填 API Setup 上测试号码下面的 Phone number ID（不是电话号码、不是 WABA ID），再重开视窗 1、2")
            return None
        number = "".join(c for c in info.get("display_phone_number", "") if c.isdigit())
        self.ok(f"WHATSAPP_PHONE_NUMBER_ID 是测试号码 …{number[-4:]}（{info.get('verified_name', '')}）")
        try:
            return self.graph(self.s.phone_number_id, params={"fields": "webhook_configuration"}).get(
                "webhook_configuration") or {}
        except GraphError:
            return {}           # 只是用来知道 Meta 送到哪个网址；问不到就用 App 的设定

    def check_waba(self, app_id: str, waba_id: str | None, candidates: list[str], subscribe: bool) -> str | None:
        """回传这个 WABA 给我们 App 设的另一个网址（override_callback_uri；一般没有）。"""
        if waba_id is None:
            for candidate in candidates:
                try:
                    numbers = self.graph(f"{candidate}/phone_numbers", params={"fields": "id"}).get("data") or []
                except GraphError as e:
                    self.info(f"问不到 WABA {candidate} 有哪些号码（{e}）")
                    continue
                if any(n.get("id") == self.s.phone_number_id for n in numbers):
                    waba_id = candidate
                    break
        if waba_id is None:
            seen = "、".join(candidates) or "token 没有列出来"
            self.bad(f"token 能用的 WhatsApp 帐号（WABA：{seen}）里，找不到测试号码",
                     "到 API Setup 看测试号码的 WhatsApp Business Account ID，再跑 python -m app.whatsapp_check --waba <ID>。"
                     "这个 ID 不在上面的清单里的话：System user → Assign assets → WhatsApp accounts 加上它（Full control），"
                     "再 Generate token 一个新的")
            return None
        if self.messaging_wabas is not None and waba_id not in self.messaging_wabas:
            self.bad(f"access token 不能用 WABA {waba_id} 发消息：Admin Platform 回复会被拒绝",
                     "System User 要加上这个 WhatsApp 帐号（Assign assets）。" + RENEW)
        try:
            apps = self.graph(f"{waba_id}/subscribed_apps").get("data") or []
        except GraphError as e:
            self.bad(f"问不到 WABA {waba_id} 订阅了哪些 App（{e}）", "确认 --waba 的 ID 是 API Setup 上的 WhatsApp Business Account ID")
            return None
        ours = next((a for a in apps if (a.get("whatsapp_business_api_data") or {}).get("id") == app_id), None)
        others = [(a.get("whatsapp_business_api_data") or {}).get("name") or "?" for a in apps if a is not ours]
        if others:
            self.info(f"WABA {waba_id} 也订阅了别的 App：{', '.join(others)}（消息也会送给它们）")
        if ours is not None:
            self.ok(f"App 已订阅 WABA {waba_id}")
            return ours.get("override_callback_uri")
        if subscribe:
            try:
                success = self.graph(f"{waba_id}/subscribed_apps", method="POST").get("success")
            except GraphError as e:
                success = False
                self.info(f"订阅失败：{e}")
            if success:
                self.ok(f"App 原本没有订阅 WABA {waba_id}，刚刚订阅好了（= README 第 9 步）")
                return None
        self.bad(f"App 没有订阅 WABA {waba_id}：Meta 只送 dashboard 的 Test，手机传的消息不会送来",
                 "执行 python -m app.whatsapp_check --subscribe（= README 第 9 步）")
        return None

    def check_app_webhook(self, app_id: str) -> str | None:
        try:
            subscriptions = self.graph(f"{app_id}/subscriptions", token=f"{app_id}|{self.s.app_secret}").get("data") or []
        except GraphError as e:
            self.bad(f"App secret 不对，或不是这个 App 的（{e}）：Meta 送来的 webhook 视窗 2 会回 401",
                     "到 App settings → Basic → App secret → Show，重新复制到 .env 的 WHATSAPP_APP_SECRET，再重开视窗 2")
            return None
        self.ok("App secret 正确")
        wa = next((x for x in subscriptions if x.get("object") == "whatsapp_business_account"), None)
        if wa is None:
            self.bad("App 没有设定 WhatsApp 的 webhook", "照 README 第 7 步在 Configuration 填 Callback URL，按 Verify and save")
            return None
        fields = [f.get("name") for f in wa.get("fields") or []]
        if "messages" in fields and wa.get("active", True):
            self.ok("App 的 webhook 订阅了 messages")
        else:
            self.bad("App 的 webhook 没有订阅 messages", "Configuration → Webhook fields → messages 按 Subscribe")
        return wa.get("callback_url")

    def effective_url(self, webhook_config: dict, waba_override: str | None, app_callback: str | None) -> str | None:
        """Meta 先用号码的另一个网址，再来是 WABA 的，最后才是 App 的 Callback URL。"""
        for label, url in (("号码另外设的网址", webhook_config.get("phone_number")),
                           ("WABA 另外设的网址", waba_override or webhook_config.get("whatsapp_business_account")),
                           ("App 的 Callback URL", webhook_config.get("application") or app_callback)):
            if url:
                self.info(f"Meta 把测试号码的消息送到：{url}（{label}）")
                if not url.rstrip("/").endswith("/webhook"):
                    self.bad("这个网址最后没有 /webhook", "Configuration 的 Callback URL 改成 https://….trycloudflare.com/webhook，再 Verify and save")
                return url
        return None

    def check_url(self, url: str) -> bool:
        challenge = secrets.token_hex(8)
        params = {"hub.mode": "subscribe", "hub.verify_token": self.s.verify_token, "hub.challenge": challenge}
        fix = ("cloudflared（视窗 3）每次重开网址都会变：把视窗 3 现在印出的网址加上 /webhook，"
               "填到 Meta 的 Configuration → Callback URL，再 Verify and save")
        try:
            r = self.http.get(url, params=params)
        except httpx.HTTPError as e:
            self.bad(f"连不上这个网址（{type(e).__name__}）：视窗 3 关了，或网址已经换了", fix)
            return False
        if r.status_code == 200 and r.text == challenge:
            self.ok("这个网址现在连得到视窗 2（tunnel 正常，暗号和 .env 一样）")
            return True
        if r.status_code == 403:
            self.bad("网址连得到，但暗号和 .env 的 WHATSAPP_VERIFY_TOKEN 不一样",
                     "改了 .env 要重开视窗 2；再到 Meta 按一次 Verify and save")
        else:
            self.bad(f"这个网址回 HTTP {r.status_code}，不是视窗 2 的 webhook 小程序（Cloudflare 的 530 / 1033 = 旧网址）", fix)
        return False

    def check_self_test(self, url: str) -> None:
        """像 Meta 一样签名送一个 webhook。里面只有一个送达状态，消息 ID 是假的、找不到，所以不会存任何东西。"""
        payload = {"object": "whatsapp_business_account", "entry": [{"id": "0", "changes": [{"field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"phone_number_id": self.s.phone_number_id},
            "statuses": [{"id": f"wamid.SELFTEST-{secrets.token_hex(8)}", "status": "delivered"}],
        }}]}]}
        body = json.dumps(payload).encode()
        signature = "sha256=" + hmac.new(self.s.app_secret.encode(), body, hashlib.sha256).hexdigest()
        try:
            r = self.http.post(url, content=body, headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature})
            received = r.json().get("received") if r.status_code == 200 else None
        except (httpx.HTTPError, ValueError, AttributeError):
            self.bad("经 tunnel 送假的 webhook 失败", "看视窗 2、3 有没有错误")
            return
        if received == 1:
            self.ok("经 tunnel 送了一个签名的假 webhook：视窗 2 收下了（视窗 2 会多一行「0 条新消息、1 个送达状态」）")
        elif r.status_code == 401:
            self.bad("视窗 2 说签名不对：视窗 2 用的 App secret 和 .env 不一样", "改了 .env 没重开视窗 2：Ctrl + C，再开一次")
        elif r.status_code == 503:
            self.bad("视窗 2 没读到 WHATSAPP_APP_SECRET / WHATSAPP_PHONE_NUMBER_ID", "重开视窗 2")
        elif r.status_code == 200:
            self.bad("视窗 2 收下了，但当成别的号码的消息", "改了 .env 的 WHATSAPP_PHONE_NUMBER_ID 没重开视窗 2：重开视窗 2")
        else:
            self.bad(f"视窗 2 回 HTTP {r.status_code}", "看视窗 2 的错误信息（500 多半是 PostgreSQL 没开）")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.whatsapp_check", description="检查 WhatsApp 的设定（Phase 5a）")
    parser.add_argument("--subscribe", action="store_true", help="App 没订阅测试的 WABA 的话，帮你订阅（README 第 9 步）")
    parser.add_argument("--waba", help="WhatsApp Business Account ID（API Setup 上有；通常不用填）")
    args = parser.parse_args(argv)
    with httpx.Client(timeout=20) as http:
        problems = Checker(get_whatsapp_settings(), http).run(waba_id=args.waba, subscribe=args.subscribe)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
