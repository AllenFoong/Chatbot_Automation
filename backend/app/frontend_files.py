"""上线时（电脑 B，D62）由 FastAPI 直接提供 Admin Platform 的网页：frontend/ 里 `npm run build` 产生的 dist/。

这样电脑 B 只要跑一个 uvicorn，不用装 Node.js；网页和 /api 是同一个网址，登录 cookie 照样带上。
开发时照旧用 Vite（http://localhost:5173）；没有 dist/ 就不提供网页。
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

DEFAULT_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def frontend_dist() -> Path | None:
    """FRONTEND_DIST（.env）或仓库的 frontend/dist；没有 index.html 就当作没有。"""
    configured = os.environ.get("FRONTEND_DIST", "").strip()
    dist = Path(configured) if configured else DEFAULT_DIST
    return dist if (dist / "index.html").is_file() else None


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """要在所有 API 路由之后呼叫：/api、/availability、/docs 先配对，剩下的才是网页。"""
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    index = dist / "index.html"
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def page(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")    # 打错的 API 网址不要回网页
        file = (dist / path).resolve()
        if path and file.is_file() and file.is_relative_to(root):
            return FileResponse(file)                                   # favicon 之类
        return FileResponse(index)                                      # /reminders 等画面：交给 React Router
