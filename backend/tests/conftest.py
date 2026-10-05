"""测试的共用设置。

PostgreSQL 测试要用环境变量 TEST_DATABASE_URL（可以写在 backend/.env），数据库名字必须以 _test 结尾：
测试开始时会删掉里面所有的表，再用 Alembic 重新建。没有设置就跳过数据库测试，其他测试照跑。
每个测试都在一个交易里跑，测试结束整个取消，测试之间互不影响。
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, make_url
from sqlalchemy.orm import Session

import app.config  # noqa: F401  载入 backend/.env
from tests.database import drop_all_tables, upgrade_to_head


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
