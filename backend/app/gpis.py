"""读取 GPiS 的预约（只读）。

只执行 SELECT（空档、提醒、检查栏位），不写入任何数据。连接前检查数据库名字，
防止不小心连到主机的正式数据库（CLAUDE.md 规则 1、2）。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Protocol

from .availability import GpisAppointment
from .reminders import ReminderAppointment

APPOINTMENTS_SQL = """
SELECT a.AppointmentID, a.TimeSlot, a.Status, a.ContactID, a.Remarks
FROM dbo.Tbl_CAH_Appointment a
WHERE a.AppointmentDate >= ?
  AND a.AppointmentDate <  ?
  AND a.DoctorID = ?
  AND ISNULL(a.Status, N'') NOT IN (N'Canceled', N'Postpone')
"""


# 提醒（Phase 5b）：那几天所有医生的预约 + 病人名字、手机号码。没有 NRIC、地址（D44）。
# 手机号码在 Qry_CAH_Appointment（统计 B10、B11 用过它的 HPNo）。取消的也读，名单上只算数量。
REMINDER_SQL = """
SELECT a.AppointmentID, a.AppointmentDate, a.TimeSlot, a.DoctorID, a.Status,
       a.ContactID, a.ContactName, a.Remarks, q.HPNo
FROM dbo.Tbl_CAH_Appointment a
LEFT JOIN dbo.Qry_CAH_Appointment q ON q.AppointmentID = a.AppointmentID
WHERE a.AppointmentDate >= ?
  AND a.AppointmentDate <  ?
"""

# 上面两条 SELECT 用到的栏位。python -m app.reminders_cli --check-gpis 会检查它们在不在（只看栏位名字）
REQUIRED_COLUMNS = {
    "Tbl_CAH_Appointment": ("AppointmentID", "AppointmentDate", "TimeSlot", "DoctorID", "Status",
                            "ContactID", "ContactName", "Remarks"),
    "Qry_CAH_Appointment": ("AppointmentID", "HPNo"),
}

COLUMNS_SQL = """
SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME IN ('Tbl_CAH_Appointment', 'Qry_CAH_Appointment')
"""


def missing_columns(found: set[tuple[str, str]]) -> list[str]:
    """found = {(表, 栏位)}；比较时不分大小写（SQL Server 也不分）。"""
    have = {(t.lower(), c.lower()) for t, c in found}
    return [f"{t}.{c}" for t, cols in REQUIRED_COLUMNS.items() for c in cols if (t.lower(), c.lower()) not in have]


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
        self.label = expected_database
        # 只有读主机的 GPiS 才是正式的资料；GPiS_Dev 里虽然是真的病人，但只能「只看名单」（D44、D54）
        self.is_production = expected_database.strip().lower() == "gpis"

    def _query(self, sql: str, *params) -> list:
        import pyodbc  # 放在这里：跑单元测试的电脑不需要装 ODBC driver

        conn = pyodbc.connect(
            self._connection_string, timeout=self._timeout, readonly=True, autocommit=True
        )
        try:
            cur = conn.cursor()
            ensure_expected_database(cur.execute("SELECT DB_NAME()").fetchval(), self._expected_database)
            return cur.execute(sql, *params).fetchall()
        finally:
            conn.close()

    def appointments_for(self, day: date, doctor_id: str) -> list[GpisAppointment]:
        start = datetime.combine(day, time.min)
        rows = self._query(APPOINTMENTS_SQL, start, start + timedelta(days=1), doctor_id.strip().upper())
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

    def reminder_appointments(self, first: date, last: date) -> list[ReminderAppointment]:
        start = datetime.combine(first, time.min)
        rows = self._query(REMINDER_SQL, start, datetime.combine(last, time.min) + timedelta(days=1))
        by_id: dict[int, ReminderAppointment] = {}
        for r in rows:
            old = by_id.get(r.AppointmentID)
            if old is not None and (old.hp_no or "").strip():
                continue    # 视图里同一个预约有几行：留第一个有号码的
            by_id[r.AppointmentID] = ReminderAppointment(
                appointment_id=r.AppointmentID,
                appointment_date=r.AppointmentDate.date() if isinstance(r.AppointmentDate, datetime)
                else r.AppointmentDate,
                time_slot=r.TimeSlot,
                doctor_id=r.DoctorID,
                status=r.Status,
                contact_id=r.ContactID,
                contact_name=r.ContactName,
                hp_no=r.HPNo,
                remarks=r.Remarks,
            )
        return list(by_id.values())

    def missing_columns(self) -> list[str]:
        return missing_columns({(r.TABLE_NAME, r.COLUMN_NAME) for r in self._query(COLUMNS_SQL)})
