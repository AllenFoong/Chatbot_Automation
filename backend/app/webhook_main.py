"""只有 WhatsApp webhook 的小程序（D35）。

开发时用 tunnel（例如 cloudflared）把它放到网上，让 Meta 把消息送进来。网上只看得到 /webhook：
看不到 Admin API、/availability（读 GPiS_Dev）和 /docs。AI_REPLIES_ENABLED 打开时，背景的 AI 回复会经
app/ai_tools.py 读 GPiS（空档、找病人），但网上还是只看得到 /webhook（D81）。

启动（在 backend/ 里）：uvicorn app.webhook_main:app --port 8001
"""

from __future__ import annotations

import logging
import re

from fastapi import FastAPI

from . import webhook

# 在视窗里看得到"收到几条消息"这类记录（只有数量和 ID，没有消息内容和电话号码，D38）
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")

_VERIFY_TOKEN = re.compile(r"(hub\.verify_token=)[^&\s]*")


class HideVerifyToken(logging.Filter):
    """uvicorn 的 access log 印出整个网址：Meta 确认 webhook 时，网址里有暗号（hub.verify_token），换成 ***。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(_VERIFY_TOKEN.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args)
        return True


logging.getLogger("uvicorn.access").addFilter(HideVerifyToken())

app = FastAPI(title="WhatsApp webhook", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(webhook.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
