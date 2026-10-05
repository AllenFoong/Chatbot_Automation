"""staff sessions：员工登录（Phase 4）

- 新表 staff_sessions：登录后的 session（只存 token 的 SHA-256）
- staff.username 一律小写（登录时会把输入转成小写再比对）

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-05 08:30:50.050987

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('staff_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('staff_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['staff_id'], ['staff.id'], name=op.f('fk_staff_sessions_staff_id_staff'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_staff_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_staff_sessions_token_hash'))
    )
    op.create_index(op.f('ix_staff_sessions_staff_id'), 'staff_sessions', ['staff_id'], unique=False)
    # autogenerate 看不到 CHECK，手动加
    op.create_check_constraint(
        op.f('ck_staff_username_lower'), 'staff', "username = lower(btrim(username)) AND username <> ''"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_staff_username_lower'), 'staff', type_='check')
    op.drop_index(op.f('ix_staff_sessions_staff_id'), table_name='staff_sessions')
    op.drop_table('staff_sessions')
