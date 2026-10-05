"""Alembic 的执行环境。

连接哪个数据库：测试时用 tests/ 传进来的连接（config.attributes["connection"]），
否则用 backend/.env 的 DATABASE_URL。表结构以 app/db/models.py 为准。
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import get_database_url
from app.db import models  # noqa: F401  载入所有的表
from app.db.base import Base

config = context.config
target_metadata = Base.metadata

if config.config_file_name and "connection" not in config.attributes:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def run_with(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    # alembic upgrade head --sql：只印出 SQL，不连接数据库
    context.configure(url=get_database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif (connection := config.attributes.get("connection")) is not None:
    run_with(connection)
else:
    with create_engine(get_database_url()).connect() as connection:
        run_with(connection)
