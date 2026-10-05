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
