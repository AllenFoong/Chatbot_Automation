"""PostgreSQL 测试用的小工具。"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Staff

BACKEND_DIR = Path(__file__).resolve().parent.parent


def alembic_config(connection: Connection) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["connection"] = connection
    return cfg


def upgrade_to_head(engine: Engine) -> None:
    with engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")


def drop_all_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        for table in conn.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).all():
            conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))


def schema_snapshot(conn: Connection, schema: str) -> set[tuple]:
    """一个 schema 里全部的栏位、约束、index（去掉 schema 名字，才能比较两个 schema）。"""
    queries = {
        "column": """
            SELECT table_name, column_name, data_type, character_maximum_length, is_nullable, column_default
            FROM information_schema.columns WHERE table_schema = :schema""",
        "constraint": """
            SELECT rel.relname, con.conname, pg_get_constraintdef(con.oid)
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace ns ON ns.oid = rel.relnamespace
            WHERE ns.nspname = :schema""",
        "index": "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = :schema",
    }
    snapshot = set()
    for kind, sql in queries.items():
        for row in conn.execute(text(sql), {"schema": schema}):
            if row[0] != "alembic_version":
                snapshot.add((kind, *(None if v is None else str(v).replace(f"{schema}.", "") for v in row)))
    return snapshot


def assert_rejected(session: Session, obj) -> None:
    """数据库应该拒绝这一行（违反 CHECK / UNIQUE / FOREIGN KEY）。"""
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(obj)


def add_staff(session: Session, username: str = "amy") -> Staff:
    staff = Staff(username=username, name=f"{username} (test)")
    session.add(staff)
    session.flush()
    return staff
