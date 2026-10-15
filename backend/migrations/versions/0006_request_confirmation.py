"""appointment_requests：谁确认的、病人有没有被通知（Phase 6a-2a，D70）

- confirmed_by：SYSTEM（每 3 分钟在 GPiS 找到了）/ STAFF（员工按的）
- patient_notified_at、patient_notified_by、patient_notified_staff_id：病人什么时候、由谁知道约好了；
  CONFIRMED 但还没有 = 要员工通知
- notify_problem：系统为什么发不了确认（超过 24 小时、这台电脑没接 WhatsApp …）
- gpis_appointment_id 加 UNIQUE：一个 GPiS 预约只能对上一个请求
- 以前就是 CONFIRMED 的：当作员工确认、员工通知过（那时候还没有自动通知）

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = 'appointment_requests'


def _done_by(name: str) -> sa.Enum:
    return sa.Enum('SYSTEM', 'STAFF', name=name, native_enum=False, create_constraint=True, length=20)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(_TABLE, sa.Column('confirmed_by', _done_by('request_confirmed_by'), nullable=True))
    op.add_column(_TABLE, sa.Column('patient_notified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(_TABLE, sa.Column('patient_notified_by', _done_by('request_notified_by'), nullable=True))
    op.add_column(_TABLE, sa.Column('patient_notified_staff_id', sa.Integer(), nullable=True))
    op.add_column(_TABLE, sa.Column('notify_problem', sa.Text(), nullable=True))
    op.create_foreign_key(op.f('fk_appointment_requests_patient_notified_staff_id_staff'), _TABLE, 'staff',
                          ['patient_notified_staff_id'], ['id'])
    op.create_unique_constraint(op.f('uq_appointment_requests_gpis_appointment_id'), _TABLE, ['gpis_appointment_id'])

    # 以前的 CONFIRMED：员工确认的，病人那时候已经由员工通知
    op.execute(
        "UPDATE appointment_requests SET confirmed_by = 'STAFF', "
        "patient_notified_at = handled_at, patient_notified_by = 'STAFF' WHERE status = 'CONFIRMED'"
    )

    # autogenerate 看不到 CHECK，手动加
    op.create_check_constraint(
        op.f('ck_appointment_requests_confirmed_by'), _TABLE,
        "(status <> 'CONFIRMED' OR confirmed_by IS NOT NULL) "
        "AND (confirmed_by IS NULL OR status IN ('CONFIRMED', 'CANCELLED'))",
    )
    op.create_check_constraint(
        op.f('ck_appointment_requests_notified_together'), _TABLE,
        "(patient_notified_at IS NULL) = (patient_notified_by IS NULL)",
    )
    op.create_check_constraint(
        op.f('ck_appointment_requests_notified_staff_only_for_staff'), _TABLE,
        "patient_notified_staff_id IS NULL OR patient_notified_by = 'STAFF'",
    )
    op.create_check_constraint(
        op.f('ck_appointment_requests_notified_after_confirmed'), _TABLE,
        "patient_notified_at IS NULL OR confirmed_by IS NOT NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    for name in ('notified_after_confirmed', 'notified_staff_only_for_staff', 'notified_together', 'confirmed_by'):
        op.drop_constraint(op.f(f'ck_appointment_requests_{name}'), _TABLE, type_='check')
    op.drop_constraint(op.f('uq_appointment_requests_gpis_appointment_id'), _TABLE, type_='unique')
    op.drop_constraint(op.f('fk_appointment_requests_patient_notified_staff_id_staff'), _TABLE, type_='foreignkey')
    op.drop_column(_TABLE, 'notify_problem')
    op.drop_column(_TABLE, 'patient_notified_staff_id')
    op.drop_column(_TABLE, 'patient_notified_by')
    op.drop_column(_TABLE, 'patient_notified_at')
    op.drop_column(_TABLE, 'confirmed_by')
