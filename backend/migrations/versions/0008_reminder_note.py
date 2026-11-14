"""提醒消息最后加的一段话（D82）

- clinic_settings：reminder_note（NULL = 不加；1–500 字）、reminder_note_updated_at、reminder_note_updated_by（员工）

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-14 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('clinic_settings', sa.Column('reminder_note', sa.Text(), nullable=True))
    op.add_column('clinic_settings', sa.Column('reminder_note_updated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('clinic_settings', sa.Column('reminder_note_updated_by', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_clinic_settings_reminder_note_updated_by_staff'), 'clinic_settings', 'staff',
                          ['reminder_note_updated_by'], ['id'])
    op.create_check_constraint(op.f('ck_clinic_settings_reminder_note_length'), 'clinic_settings',
                               'char_length(reminder_note) BETWEEN 1 AND 500')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_clinic_settings_reminder_note_length'), 'clinic_settings', type_='check')
    op.drop_constraint(op.f('fk_clinic_settings_reminder_note_updated_by_staff'), 'clinic_settings',
                       type_='foreignkey')
    op.drop_column('clinic_settings', 'reminder_note_updated_by')
    op.drop_column('clinic_settings', 'reminder_note_updated_at')
    op.drop_column('clinic_settings', 'reminder_note')
