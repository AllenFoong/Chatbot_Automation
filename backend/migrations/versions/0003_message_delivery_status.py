"""message delivery status：发出的消息送到哪一步（Phase 5）

- messages.wa_status：ACCEPTED / SENT / DELIVERED / READ / FAILED（WhatsApp 的 status webhook 更新）
- messages.wa_error：送不到的原因
- 只有发出的消息有 wa_status；只有 FAILED 有 wa_error

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-06 06:27:40.218951

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('messages', sa.Column('wa_status', sa.Enum('ACCEPTED', 'SENT', 'DELIVERED', 'READ', 'FAILED', name='message_wa_status', native_enum=False, create_constraint=True, length=20), nullable=True))
    op.add_column('messages', sa.Column('wa_error', sa.Text(), nullable=True))
    # autogenerate 看不到 CHECK，手动加
    op.create_check_constraint(
        op.f('ck_messages_wa_status_only_outgoing'), 'messages', "wa_status IS NULL OR sender <> 'CUSTOMER'"
    )
    op.create_check_constraint(
        op.f('ck_messages_wa_error_only_failed'), 'messages', "wa_error IS NULL OR wa_status = 'FAILED'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_messages_wa_error_only_failed'), 'messages', type_='check')
    op.drop_constraint(op.f('ck_messages_wa_status_only_outgoing'), 'messages', type_='check')
    op.drop_column('messages', 'wa_error')
    op.drop_column('messages', 'wa_status')
