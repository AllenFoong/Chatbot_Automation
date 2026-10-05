"""连接本系统的 PostgreSQL（backend/.env 的 DATABASE_URL）。"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_database_url


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_database_url(), pool_pre_ping=True)


@lru_cache
def _sessions() -> sessionmaker[Session]:
    return sessionmaker(get_engine())


def new_session() -> Session:
    """用法：with new_session() as session: …；改了资料要自己 session.commit()。"""
    return _sessions()()


def get_session() -> Iterator[Session]:
    """FastAPI dependency：每个请求一个 session，请求结束就关闭（没有 commit 的改动会取消）。"""
    with new_session() as session:
        yield session
