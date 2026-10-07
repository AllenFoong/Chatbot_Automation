"""从环境变量 / backend/.env 读取设置。.env 不进仓库（见 .env.example）。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class Settings:
    gpis_connection_string: str
    gpis_expected_database: str


def get_settings() -> Settings:
    conn = os.environ.get("GPIS_CONNECTION_STRING", "").strip()
    if not conn:
        raise RuntimeError("没有设置 GPIS_CONNECTION_STRING：复制 backend/.env.example 为 backend/.env 再填写")
    return Settings(
        gpis_connection_string=conn,
        gpis_expected_database=os.environ.get("GPIS_EXPECTED_DATABASE", "GPiS_Dev").strip(),
    )


def cookie_secure() -> bool:
    """登录 cookie 只经 https 传送。开发电脑用 http://localhost，所以默认 false；上线（https）时改成 true。"""
    return os.environ.get("COOKIE_SECURE", "false").strip().lower() == "true"


def get_database_url() -> str:
    """本系统的 PostgreSQL（Phase 3）。"""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("没有设置 DATABASE_URL：在 backend/.env 加上（格式见 .env.example）")
    return url


@dataclass(frozen=True)
class WhatsAppSettings:
    """WhatsApp Cloud API（Phase 5）。值都在 backend/.env；token、secret 绝不写进仓库。"""

    verify_token: str           # 自己想的一串字，Meta 设定 webhook 时用来确认是我们的服务器
    app_secret: str             # Meta App 的 App Secret：检查 webhook 真的是 Meta 送来的
    access_token: str           # 发消息用
    phone_number_id: str        # 发消息的号码（开发时 = Meta 的测试号码）
    api_version: str
    allowed_recipients: frozenset[str] | None    # 只能发给这些号码；None = 谁都可以（只有上线才用）

    def can_send_to(self, wa_phone: str) -> bool:
        return self.allowed_recipients is None or wa_phone in self.allowed_recipients


def get_whatsapp_settings() -> WhatsAppSettings:
    from .phone import normalize_phone

    def env(name: str, default: str = "") -> str:
        return os.environ.get(name, default).strip()

    # 开发时只能发给自己的测试号码（D34）：没设定 = 谁都不能发；"*" = 谁都可以（上线才用）
    raw = env("WHATSAPP_ALLOWED_RECIPIENTS")
    allowed = None if raw == "*" else frozenset(
        p for p in (normalize_phone(x) for x in raw.split(",")) if p
    )
    return WhatsAppSettings(
        verify_token=env("WHATSAPP_VERIFY_TOKEN"),
        app_secret=env("WHATSAPP_APP_SECRET"),
        access_token=env("WHATSAPP_ACCESS_TOKEN"),
        phone_number_id=env("WHATSAPP_PHONE_NUMBER_ID"),
        api_version=env("WHATSAPP_API_VERSION", "v26.0"),
        allowed_recipients=allowed,
    )


def ai_replies_enabled() -> bool:
    """AI 回复（Phase 6）。还没有 AI 时是 false：病人的新对话直接交给员工（D37）。"""
    return os.environ.get("AI_REPLIES_ENABLED", "false").strip().lower() == "true"
