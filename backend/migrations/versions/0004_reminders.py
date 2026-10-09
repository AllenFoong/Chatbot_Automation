"""reminders：预约提醒做过什么、哪些号码不要提醒（Phase 5b）

- 新表 reminders：一个号码、一个预约日期一条（UNIQUE）；现在只记员工按过 Open in WhatsApp（OPENED）、
  没有发出去（NOT_SENT）、打开时的消息和包括哪几个 GPiS 预约
- wa_contacts.reminders_opt_out_*：这个号码不要提醒（例：签名表写 NO WA，D55）

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('reminders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('appointment_date', sa.Date(), nullable=False),
    sa.Column('wa_phone', sa.String(length=20), nullable=False),
    sa.Column('status', sa.Enum('OPENED', 'NOT_SENT', name='reminder_status', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('gpis_appointment_ids', postgresql.ARRAY(sa.Integer()), nullable=False),
    sa.Column('staff_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("wa_phone ~ '^[0-9]{8,15}$'", name=op.f('ck_reminders_wa_phone_digits')),
    sa.ForeignKeyConstraint(['staff_id'], ['staff.id'], name=op.f('fk_reminders_staff_id_staff')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reminders')),
    sa.UniqueConstraint('appointment_date', 'wa_phone', name=op.f('uq_reminders_appointment_date_wa_phone'))
    )
    op.add_column('wa_contacts', sa.Column('reminders_opt_out_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('wa_contacts', sa.Column('reminders_opt_out_by', sa.Enum('PATIENT', 'STAFF', name='opt_out_by', native_enum=False, create_constraint=True, length=20), nullable=True))
    op.add_column('wa_contacts', sa.Column('reminders_opt_out_staff_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_wa_contacts_reminders_opt_out_staff_id_staff'), 'wa_contacts', 'staff', ['reminders_opt_out_staff_id'], ['id'])
    # autogenerate 看不到 CHECK，手动加
    op.create_check_constraint(
        op.f('ck_wa_contacts_opt_out_together'), 'wa_contacts', "(reminders_opt_out_at IS NULL) = (reminders_opt_out_by IS NULL)"
    )
    op.create_check_constraint(
        op.f('ck_wa_contacts_opt_out_staff_only_for_staff'), 'wa_contacts',
        "reminders_opt_out_staff_id IS NULL OR reminders_opt_out_by = 'STAFF'",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_wa_contacts_opt_out_staff_only_for_staff'), 'wa_contacts', type_='check')
    op.drop_constraint(op.f('ck_wa_contacts_opt_out_together'), 'wa_contacts', type_='check')
    op.drop_constraint(op.f('fk_wa_contacts_reminders_opt_out_staff_id_staff'), 'wa_contacts', type_='foreignkey')
    op.drop_column('wa_contacts', 'reminders_opt_out_staff_id')
    op.drop_column('wa_contacts', 'reminders_opt_out_by')
    op.drop_column('wa_contacts', 'reminders_opt_out_at')
    op.drop_table('reminders')
