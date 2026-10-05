"""所有表的基础类别。

约束（constraint）用固定规则命名：以后用 Alembic 修改表结构时，才找得到要改的是哪一个。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # 所有时间点都存成 timestamptz（绝对时间）；Admin Platform 显示时再转成马来西亚时间
    type_annotation_map = {datetime: DateTime(timezone=True)}
