"""电脑 B 上由 FastAPI 提供网页（D62）。用假的 dist/，不用真的 npm run build。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import frontend_files
from app.frontend_files import frontend_dist, mount_frontend


def _app(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>", encoding="utf-8")
    (tmp_path / "assets" / "index-abc.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path.parent / "secret.txt").write_text("not for the browser", encoding="utf-8")
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    mount_frontend(app, tmp_path)
    return TestClient(app)


def test_pages_api_and_files(tmp_path):
    client = _app(tmp_path)
    assert client.get("/api/ping").json() == {"ok": True}                  # API 先配对
    assert client.get("/").text == "<div id=root></div>"
    assert client.get("/reminders").text == "<div id=root></div>"          # React Router 的画面
    assert client.get("/assets/index-abc.js").text == "console.log(1)"
    assert client.get("/favicon.svg").text == "<svg/>"


def test_wrong_api_address_is_404_not_the_page(tmp_path):
    client = _app(tmp_path)
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json() == {"detail": "Not Found"}


def test_files_outside_dist_are_not_served(tmp_path):
    client = _app(tmp_path)
    assert "not for the browser" not in client.get("/../secret.txt").text
    assert "not for the browser" not in client.get("/%2e%2e/secret.txt").text


def test_no_dist_means_no_page(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path / "missing"))
    assert frontend_dist() is None
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path))
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    assert frontend_dist() == tmp_path
    monkeypatch.delenv("FRONTEND_DIST")
    assert frontend_dist() in (None, frontend_files.DEFAULT_DIST)
