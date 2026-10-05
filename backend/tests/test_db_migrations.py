"""Alembic migration：建出来的表要和 app/db/models.py 一模一样，而且拆得掉、能重建。"""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from app.db.base import Base
from tests.database import alembic_config, schema_snapshot


def test_models_match_migrations(db_engine):
    with db_engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []


def test_migrations_create_exactly_the_models(db_engine):
    """compare_metadata 不比较 CHECK：另外照 models.py 建一份，连约束、index 一起比。"""
    with db_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS models_check CASCADE"))
        conn.execute(text("CREATE SCHEMA models_check"))
        try:
            Base.metadata.create_all(conn.execution_options(schema_translate_map={None: "models_check"}))
            assert schema_snapshot(conn, "public") == schema_snapshot(conn, "models_check")
        finally:
            conn.execute(text("DROP SCHEMA models_check CASCADE"))


def test_downgrade_and_upgrade_again(db_engine):
    with db_engine.begin() as conn:
        command.downgrade(alembic_config(conn), "base")
        assert inspect(conn).get_table_names() == ["alembic_version"]
        command.upgrade(alembic_config(conn), "head")
        assert set(inspect(conn).get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
