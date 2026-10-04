"""读取 GPiS 的预约（只读）。

只执行一条 SELECT，不写入任何数据。连接前检查数据库名字，
防止不小心连到主机的正式数据库（CLAUDE.md 规则 1、2）。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Protocol

from .availability import GpisAppointment

APPOINTMENTS_SQL = """
SELECT a.AppointmentID, a.TimeSlot, a.Status, a.ContactID, a.Remarks
FROM dbo.Tbl_CAH_Appointment a
WHERE a.AppointmentDate >= ?
  AND a.AppointmentDate <  ?
  AND a.DoctorID = ?
  AND ISNULL(a.Status, N'') NOT IN (N'Canceled', N'Postpone')
"""


class AppointmentSource(Protocol):
    def appointments_for(self, day: date, doctor_id: str) -> list[GpisAppointment]: ...


class WrongDatabaseError(RuntimeError):
    pass


def ensure_expected_database(actual: str | None, expected: str) -> None:
    if (actual or "").lower() != expected.lower():
        raise WrongDatabaseError(
            f"连接到的数据库是 {actual!r}，不是设置的 {expected!r}。为了安全，拒绝读取。"
        )


class GpisReader:
    """每次查询都重新读 GPiS（员工会删改预约，W26），不做缓存。"""

    def __init__(self, connection_string: str, expected_database: str, timeout: int = 10):
        self._connection_string = connection_string
        self._expected_database = expected_database
        self._timeout = timeout

    def appointments_for(self, day: date, doctor_id: str) -> list[GpisAppointment]:
        import pyodbc  # 放在这里：跑单元测试的电脑不需要装 ODBC driver

        start = datetime.combine(day, time.min)
        conn = pyodbc.connect(
            self._connection_string, timeout=self._timeout, readonly=True, autocommit=True
        )
        try:
            cur = conn.cursor()
            ensure_expected_database(cur.execute("SELECT DB_NAME()").fetchval(), self._expected_database)
            rows = cur.execute(
                APPOINTMENTS_SQL, start, start + timedelta(days=1), doctor_id.strip().upper()
            ).fetchall()
        finally:
            conn.close()

        return [
            GpisAppointment(
                appointment_id=r.AppointmentID,
                time_slot=r.TimeSlot,
                status=r.Status,
                contact_id=r.ContactID,
                remarks=r.Remarks,
            )
            for r in rows
        ]
