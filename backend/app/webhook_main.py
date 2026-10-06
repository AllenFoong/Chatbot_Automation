"""只有 WhatsApp webhook 的小程序（D35）。

开发时用 tunnel（例如 cloudflared）把它放到网上，让 Meta 把消息送进来。网上只看得到 /webhook：
看不到 Admin API、/availability（读 GPiS_Dev）和 /docs。它只连本系统的 PostgreSQL，不连 GPiS。

启动（在 backend/ 里）：uvicorn app.webhook_main:app --port 8001
"""

from __future__ import annotations

from fastapi import FastAPI

from . import webhook

app = FastAPI(title="WhatsApp webhook", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(webhook.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
