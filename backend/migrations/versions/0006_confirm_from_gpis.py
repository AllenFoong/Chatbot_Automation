"""appointment_requests：确认时点选的 GPiS 预约、通知病人（Phase 6a-2b，D71）

- confirmed_date / confirmed_slot / confirmed_doctor_id：员工点选的 GPiS 预约当时的日期、时间、医生
- confirm_message、patient_told_at、patient_told_by、notify_problem：确认消息和「要通知」
- 一个 GPiS AppointmentID 只能确认一个请求（CONFIRMED 的部分唯一 index）
- 以前确认的请求（这一版之前，没有通知的功能）当作已经通知：patient_told_at = handled_at

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-15 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('appointment_requests', sa.Column('confirmed_date', sa.Date(), nullable=True))
    op.add_column('appointment_requests', sa.Column('confirmed_slot', sa.Time(), nullable=True))
    op.add_column('appointment_requests', sa.Column('confirmed_doctor_id', sa.String(length=20), nullable=True))
    op.add_column('appointment_requests', sa.Column('confirm_message', sa.Text(), nullable=True))
    op.add_column('appointment_requests', sa.Column('patient_told_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('appointment_requests', sa.Column('patient_told_by', sa.Integer(), nullable=True))
    op.add_column('appointment_requests', sa.Column('notify_problem', sa.Text(), nullable=True))
    op.create_foreign_key(op.f('fk_appointment_requests_patient_told_by_staff'), 'appointment_requests', 'staff',
                          ['patient_told_by'], ['id'])
    op.create_check_constraint(op.f('ck_appointment_requests_told_by_needs_time'), 'appointment_requests',
                               'patient_told_by IS NULL OR patient_told_at IS NOT NULL')
    op.execute("UPDATE appointment_requests SET patient_told_at = handled_at WHERE status = 'CONFIRMED'")
    op.create_index('uq_appointment_requests_confirmed_gpis_id', 'appointment_requests', ['gpis_appointment_id'],
                    unique=True, postgresql_where=sa.text("status = 'CONFIRMED'"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_appointment_requests_confirmed_gpis_id', table_name='appointment_requests',
                  postgresql_where=sa.text("status = 'CONFIRMED'"))
    op.drop_constraint(op.f('ck_appointment_requests_told_by_needs_time'), 'appointment_requests', type_='check')
    op.drop_constraint(op.f('fk_appointment_requests_patient_told_by_staff'), 'appointment_requests',
                       type_='foreignkey')
    for column in ('notify_problem', 'patient_told_by', 'patient_told_at', 'confirm_message',
                   'confirmed_doctor_id', 'confirmed_slot', 'confirmed_date'):
        op.drop_column('appointment_requests', column)
