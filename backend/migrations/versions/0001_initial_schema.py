"""initial schema：Phase 3 的全部表（和 app/db/models.py 一样）

诊所设置：doctors、doctor_schedules、services、clinic_closures、doctor_leaves、clinic_settings
对话和预约请求：staff、wa_contacts、conversations、messages、customers、appointment_requests
设置的初始值不在这里：建好表之后执行 python -m app.db.seed

Revision ID: 0001
Revises:
Create Date: 2026-10-05 02:14:34.717020

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('clinic_closures',
    sa.Column('closure_date', sa.Date(), nullable=False),
    sa.Column('reason', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('closure_date', name=op.f('pk_clinic_closures'))
    )
    op.create_table('clinic_settings',
    sa.Column('id', sa.SmallInteger(), server_default=sa.text('1'), autoincrement=False, nullable=False),
    sa.Column('max_per_slot', sa.SmallInteger(), server_default=sa.text('3'), nullable=False),
    sa.Column('max_per_slot_for_ai', sa.SmallInteger(), server_default=sa.text('3'), nullable=False),
    sa.Column('clinic_contact_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('id = 1', name=op.f('ck_clinic_settings_single_row')),
    sa.CheckConstraint('max_per_slot BETWEEN 1 AND 3', name=op.f('ck_clinic_settings_max_per_slot')),
    sa.CheckConstraint('max_per_slot_for_ai BETWEEN 1 AND 3', name=op.f('ck_clinic_settings_max_per_slot_for_ai')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_clinic_settings'))
    )
    op.create_table('customers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('gpis_contact_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("phone ~ '^[0-9]{8,15}$'", name=op.f('ck_customers_phone_digits')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_customers')),
    sa.UniqueConstraint('gpis_contact_id', name=op.f('uq_customers_gpis_contact_id'))
    )
    op.create_index(op.f('ix_customers_phone'), 'customers', ['phone'], unique=False)
    op.create_table('doctors',
    sa.Column('id', sa.String(length=20), nullable=False),
    sa.Column('display_name', sa.String(length=100), nullable=False),
    sa.Column('remark_tag', sa.String(length=5), nullable=True),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.CheckConstraint('id = upper(btrim(id))', name=op.f('ck_doctors_id_upper')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_doctors'))
    )
    op.create_table('services',
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('can_be_third', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('may_need_1h', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('ai_can_book', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('treatment_group', sa.String(length=20), nullable=True),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.CheckConstraint('code = upper(btrim(code))', name=op.f('ck_services_code_upper')),
    sa.PrimaryKeyConstraint('code', name=op.f('pk_services'))
    )
    op.create_table('staff',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('role', sa.Enum('ADMIN', 'STAFF', name='staff_role', native_enum=False, create_constraint=True, length=20), server_default='STAFF', nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_staff')),
    sa.UniqueConstraint('username', name=op.f('uq_staff_username'))
    )
    op.create_table('wa_contacts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('wa_phone', sa.String(length=20), nullable=False),
    sa.Column('profile_name', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("wa_phone ~ '^[0-9]{8,15}$'", name=op.f('ck_wa_contacts_wa_phone_digits')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wa_contacts')),
    sa.UniqueConstraint('wa_phone', name=op.f('uq_wa_contacts_wa_phone'))
    )
    op.create_table('conversations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('wa_contact_id', sa.Integer(), nullable=False),
    sa.Column('mode', sa.Enum('BOT', 'HUMAN', 'CLOSED', name='conversation_mode', native_enum=False, create_constraint=True, length=20), server_default='BOT', nullable=False),
    sa.Column('assigned_staff_id', sa.Integer(), nullable=True),
    sa.Column('handover_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("(mode = 'CLOSED') = (closed_at IS NOT NULL)", name=op.f('ck_conversations_closed_at')),
    sa.ForeignKeyConstraint(['assigned_staff_id'], ['staff.id'], name=op.f('fk_conversations_assigned_staff_id_staff')),
    sa.ForeignKeyConstraint(['wa_contact_id'], ['wa_contacts.id'], name=op.f('fk_conversations_wa_contact_id_wa_contacts')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations'))
    )
    op.create_index(op.f('ix_conversations_wa_contact_id'), 'conversations', ['wa_contact_id'], unique=False)
    op.create_index('uq_conversations_open_per_contact', 'conversations', ['wa_contact_id'], unique=True, postgresql_where=sa.text("mode <> 'CLOSED'"))
    op.create_table('doctor_leaves',
    sa.Column('doctor_id', sa.String(length=20), nullable=False),
    sa.Column('leave_date', sa.Date(), nullable=False),
    sa.Column('reason', sa.String(length=100), nullable=True),
    sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], name=op.f('fk_doctor_leaves_doctor_id_doctors'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('doctor_id', 'leave_date', name=op.f('pk_doctor_leaves'))
    )
    op.create_table('doctor_schedules',
    sa.Column('doctor_id', sa.String(length=20), nullable=False),
    sa.Column('weekday', sa.SmallInteger(), nullable=False),
    sa.Column('is_working', sa.Boolean(), nullable=False),
    sa.Column('start_time', sa.Time(), nullable=True),
    sa.Column('last_slot', sa.Time(), nullable=True),
    sa.Column('break_start', sa.Time(), nullable=True),
    sa.Column('break_end', sa.Time(), nullable=True),
    sa.CheckConstraint('(break_start IS NULL) = (break_end IS NULL) AND (break_start IS NULL OR break_start < break_end)', name=op.f('ck_doctor_schedules_break')),
    sa.CheckConstraint('NOT is_working OR (start_time IS NOT NULL AND last_slot IS NOT NULL AND start_time <= last_slot)', name=op.f('ck_doctor_schedules_working_hours')),
    sa.CheckConstraint('break_end IS NULL OR (EXTRACT(MINUTE FROM break_end) IN (0, 30) AND EXTRACT(SECOND FROM break_end) = 0)', name=op.f('ck_doctor_schedules_break_end_on_grid')),
    sa.CheckConstraint('break_start IS NULL OR (EXTRACT(MINUTE FROM break_start) IN (0, 30) AND EXTRACT(SECOND FROM break_start) = 0)', name=op.f('ck_doctor_schedules_break_start_on_grid')),
    sa.CheckConstraint('last_slot IS NULL OR (EXTRACT(MINUTE FROM last_slot) IN (0, 30) AND EXTRACT(SECOND FROM last_slot) = 0)', name=op.f('ck_doctor_schedules_last_slot_on_grid')),
    sa.CheckConstraint('start_time IS NULL OR (EXTRACT(MINUTE FROM start_time) IN (0, 30) AND EXTRACT(SECOND FROM start_time) = 0)', name=op.f('ck_doctor_schedules_start_time_on_grid')),
    sa.CheckConstraint('weekday BETWEEN 1 AND 7', name=op.f('ck_doctor_schedules_weekday')),
    sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], name=op.f('fk_doctor_schedules_doctor_id_doctors'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('doctor_id', 'weekday', name=op.f('pk_doctor_schedules'))
    )
    op.create_table('appointment_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('conversation_id', sa.Integer(), nullable=True),
    sa.Column('service_code', sa.String(length=20), nullable=False),
    sa.Column('doctor_id', sa.String(length=20), nullable=True),
    sa.Column('preferred_date', sa.Date(), nullable=True),
    sa.Column('preferred_slot', sa.Time(), nullable=True),
    sa.Column('duration_minutes', sa.SmallInteger(), server_default=sa.text('30'), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'CONFIRMED', 'REJECTED', 'CANCELLED', name='request_status', native_enum=False, create_constraint=True, length=20), server_default='PENDING', nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('group_id', sa.Uuid(), nullable=True),
    sa.Column('gpis_appointment_id', sa.Integer(), nullable=True),
    sa.Column('handled_by', sa.Integer(), nullable=True),
    sa.Column('handled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(status = 'PENDING') = (handled_at IS NULL)", name=op.f('ck_appointment_requests_handled_at')),
    sa.CheckConstraint('duration_minutes > 0 AND mod(duration_minutes, 30) = 0', name=op.f('ck_appointment_requests_duration')),
    sa.CheckConstraint('preferred_slot IS NULL OR (EXTRACT(MINUTE FROM preferred_slot) IN (0, 30) AND EXTRACT(SECOND FROM preferred_slot) = 0)', name=op.f('ck_appointment_requests_preferred_slot_on_grid')),
    sa.CheckConstraint('preferred_slot IS NULL OR preferred_date IS NOT NULL', name=op.f('ck_appointment_requests_slot_needs_date')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_appointment_requests_conversation_id_conversations')),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_appointment_requests_customer_id_customers')),
    sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], name=op.f('fk_appointment_requests_doctor_id_doctors')),
    sa.ForeignKeyConstraint(['handled_by'], ['staff.id'], name=op.f('fk_appointment_requests_handled_by_staff')),
    sa.ForeignKeyConstraint(['service_code'], ['services.code'], name=op.f('fk_appointment_requests_service_code_services')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_appointment_requests'))
    )
    op.create_index(op.f('ix_appointment_requests_conversation_id'), 'appointment_requests', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_appointment_requests_customer_id'), 'appointment_requests', ['customer_id'], unique=False)
    op.create_table('messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('conversation_id', sa.Integer(), nullable=False),
    sa.Column('sender', sa.Enum('CUSTOMER', 'BOT', 'STAFF', name='message_sender', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.Column('staff_id', sa.Integer(), nullable=True),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('wa_message_id', sa.String(length=128), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("staff_id IS NULL OR sender = 'STAFF'", name=op.f('ck_messages_staff_id_only_for_staff')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_messages_conversation_id_conversations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['staff_id'], ['staff.id'], name=op.f('fk_messages_staff_id_staff')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages')),
    sa.UniqueConstraint('wa_message_id', name=op.f('uq_messages_wa_message_id'))
    )
    op.create_index(op.f('ix_messages_conversation_id'), 'messages', ['conversation_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_messages_conversation_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_appointment_requests_customer_id'), table_name='appointment_requests')
    op.drop_index(op.f('ix_appointment_requests_conversation_id'), table_name='appointment_requests')
    op.drop_table('appointment_requests')
    op.drop_table('doctor_schedules')
    op.drop_table('doctor_leaves')
    op.drop_index('uq_conversations_open_per_contact', table_name='conversations', postgresql_where=sa.text("mode <> 'CLOSED'"))
    op.drop_index(op.f('ix_conversations_wa_contact_id'), table_name='conversations')
    op.drop_table('conversations')
    op.drop_table('wa_contacts')
    op.drop_table('staff')
    op.drop_table('services')
    op.drop_table('doctors')
    op.drop_index(op.f('ix_customers_phone'), table_name='customers')
    op.drop_table('customers')
    op.drop_table('clinic_settings')
    op.drop_table('clinic_closures')
