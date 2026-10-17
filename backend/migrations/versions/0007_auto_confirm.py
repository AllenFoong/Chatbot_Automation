"""自动确认（Phase 6a-2c，D71 ②、D74）

- clinic_settings：auto_confirm（只有 ADMIN 能改，默认关）、auto_confirm_checked_at（上次成功查 GPiS）、auto_confirm_error
- appointment_requests.gpis_same_day_before：系统第一次看这个请求那天时，病人在 GPiS 已经有没有预约（NULL = 还没看过）

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-17 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('clinic_settings', sa.Column('auto_confirm', sa.Boolean(), server_default=sa.false(),
                                               nullable=False))
    op.add_column('clinic_settings', sa.Column('auto_confirm_checked_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('clinic_settings', sa.Column('auto_confirm_error', sa.Text(), nullable=True))
    op.add_column('appointment_requests', sa.Column('gpis_same_day_before', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('appointment_requests', 'gpis_same_day_before')
    op.drop_column('clinic_settings', 'auto_confirm_error')
    op.drop_column('clinic_settings', 'auto_confirm_checked_at')
    op.drop_column('clinic_settings', 'auto_confirm')
