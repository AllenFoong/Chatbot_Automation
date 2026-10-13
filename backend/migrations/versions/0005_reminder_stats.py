"""reminder_stats：提醒删掉之后留下的每天数目（A10）

- 新表 reminder_stats：一个预约日期一行（opened、not_sent、opened_appointments），没有号码、名字、员工
- reminders 本身没有改：预约日期过了 90 天的整行删掉，由 app/db/retention.py 做（D67）

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-13 14:20:52.067476

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('reminder_stats',
    sa.Column('appointment_date', sa.Date(), nullable=False),
    sa.Column('opened', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('not_sent', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('opened_appointments', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.CheckConstraint('opened >= 0 AND not_sent >= 0 AND opened_appointments >= 0', name=op.f('ck_reminder_stats_counts')),
    sa.PrimaryKeyConstraint('appointment_date', name=op.f('pk_reminder_stats'))
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('reminder_stats')
