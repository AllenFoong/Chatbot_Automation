"""测试的共用设置。

PostgreSQL 测试要用环境变量 TEST_DATABASE_URL（可以写在 backend/.env），数据库名字必须以 _test 结尾：
测试开始时会删掉里面所有的表，再用 Alembic 重新建。没有设置就跳过数据库测试，其他测试照跑。
每个测试都在一个交易里跑，测试结束整个取消，测试之间互不影响。
"""

from __future__ import annotations

import os

import pytest
from argon2 import PasswordHasher
from sqlalchemy import create_engine, make_url
from sqlalchemy.orm import Session

import app.config  # noqa: F401  载入 backend/.env
from tests.database import PASSWORD, drop_all_tables, upgrade_to_head


@pytest.fixture(autouse=True)
def _no_auto_confirm_loop(monkeypatch):
    """测试不开背景的自动确认（app/main.py 的 lifespan）。"""
    monkeypatch.setenv("AUTO_CONFIRM_LOOP", "off")


@pytest.fixture(autouse=True)
def _never_use_dev_database(monkeypatch):
    """测试绝不能连 DATABASE_URL（开发用的数据库），只能用 TEST_DATABASE_URL。"""

    def forbidden():
        raise AssertionError("测试不能连 DATABASE_URL：请用 session fixture（TEST_DATABASE_URL）")

    monkeypatch.setattr("app.db.session.get_engine", forbidden)


@pytest.fixture(scope="session")
def db_engine():
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("没有设置 TEST_DATABASE_URL，跳过 PostgreSQL 测试（见 backend/README.md）")
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        pytest.exit(f"TEST_DATABASE_URL 的数据库是 {name!r}，名字不是以 _test 结尾。测试会清空数据库，拒绝执行。",
                    returncode=1)
    engine = create_engine(url)
    drop_all_tables(engine)
    upgrade_to_head(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(db_engine):
    """一个测试一个交易；里面的 commit 只到 savepoint，测试结束整个取消。"""
    with db_engine.connect() as conn:
        trans = conn.begin()
        s = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield s
        finally:
            s.close()
            trans.rollback()


@pytest.fixture
def client_for(session, monkeypatch):
    """client_for(username)：已经登录的 TestClient，连测试数据库。每个员工一个（各有自己的 cookie）。

    用法：add_staff(session, "amy", password=PASSWORD)，再 client_for("amy")。
    """
    from fastapi.testclient import TestClient

    from app.db.session import get_session
    from app.main import app

    # 测试里密码加密用低成本参数，跑得快（正式的设置在 app/auth.py）
    monkeypatch.setattr("app.auth._hasher", PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1))

    def use_test_session():
        try:
            yield session
        except Exception:
            session.rollback()       # 和正式的一样：出错时取消这个请求的改动
            raise

    app.dependency_overrides[get_session] = use_test_session

    def make(username: str | None = None, password: str = PASSWORD) -> TestClient:
        client = TestClient(app)
        if username is not None:
            r = client.post("/api/auth/login", json={"username": username, "password": password})
            assert r.status_code == 200, r.text
        return client

    yield make
    app.dependency_overrides.clear()
