"""读取 GPiS 的预约（只读）。

只执行 SELECT（空档、提醒、检查栏位），不写入任何数据。连接前检查数据库名字，
防止不小心连到主机的正式数据库（CLAUDE.md 规则 1、2）。
读主机的 GPiS 时还要确认用的是只读帐号（D52，sql/create_readonly_login.sql）：不是的话拒绝读取。
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


# 连接用的帐号能做什么（D52）。只看权限，不读任何资料（也不读 Tbl_User，规则 5）。
_OBJECT = "QUOTENAME(SCHEMA_NAME(o.schema_id)) + '.' + QUOTENAME(o.name)"


def _database_perms(*names: str) -> str:
    """有几个数据库层的权限。查不到（NULL）当作有，宁可拒绝。"""
    return " + ".join(f"ISNULL(HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', '{n}'), 1)" for n in names)


# GPiS 的数据库把 CREATE TABLE、BACKUP DATABASE 等给了 public（每个帐号都自动有），D60
PERMISSIONS_SQL = f"""
SELECT SUSER_SNAME() AS LoginName,
       IS_SRVROLEMEMBER('sysadmin') AS IsSysadmin,
       HAS_PERMS_BY_NAME('dbo.Tbl_CAH_Appointment', 'OBJECT', 'SELECT') AS ReadAppointments,
       HAS_PERMS_BY_NAME('dbo.Qry_CAH_Appointment', 'OBJECT', 'SELECT') AS ReadView,
       HAS_PERMS_BY_NAME('dbo.Tbl_User', 'OBJECT', 'SELECT') AS ReadUsers,
       {_database_perms('ALTER', 'CREATE TABLE', 'CREATE VIEW', 'CREATE PROCEDURE', 'CREATE FUNCTION',
                        'CREATE RULE', 'CREATE DEFAULT', 'CREATE TYPE', 'CREATE SCHEMA')} AS ChangeDatabase,
       {_database_perms('BACKUP DATABASE', 'BACKUP LOG')} AS BackupDatabase,
       (SELECT COUNT(*) FROM sys.objects o WHERE o.type IN ('U', 'V') AND o.is_ms_shipped = 0
          AND (HAS_PERMS_BY_NAME({_OBJECT}, 'OBJECT', 'INSERT') = 1
            OR HAS_PERMS_BY_NAME({_OBJECT}, 'OBJECT', 'UPDATE') = 1
            OR HAS_PERMS_BY_NAME({_OBJECT}, 'OBJECT', 'DELETE') = 1)) AS WritableObjects,
       (SELECT COUNT(*) FROM sys.objects o WHERE o.type IN ('P', 'PC', 'X') AND o.is_ms_shipped = 0
          AND HAS_PERMS_BY_NAME({_OBJECT}, 'OBJECT', 'EXECUTE') = 1) AS ExecutableProcedures,
       (SELECT COUNT(*) FROM sys.objects o WHERE o.type IN ('U', 'V') AND o.is_ms_shipped = 0
          AND HAS_PERMS_BY_NAME({_OBJECT}, 'OBJECT', 'SELECT') = 1) AS ReadableObjects
"""

READONLY_LOGIN_TABLES = 2      # 只读帐号只给 Tbl_CAH_Appointment、Qry_CAH_Appointment（sql/create_readonly_login.sql）


def permission_problems(r) -> tuple[list[str], list[str]]:
    """(问题, 提醒)。有「问题」的帐号不能拿来读主机的 GPiS；「提醒」= 权限比需要的多，但不能写。"""
    problems: list[str] = []
    if r.IsSysadmin:
        problems.append(f"{r.LoginName} 是 sysadmin，什么都能改")
    if r.ChangeDatabase:
        problems.append("可以改数据库的结构")
    if r.BackupDatabase:
        problems.append("可以备份整个数据库（包括所有病人资料和 Tbl_User）")
    if r.WritableObjects:
        problems.append(f"可以写入 {r.WritableObjects} 个表或视图")
    if r.ExecutableProcedures:
        problems.append(f"可以执行 {r.ExecutableProcedures} 个 stored procedure（可能会写入）")
    if r.ReadUsers:
        problems.append("读得到 Tbl_User（D52：不能给）")
    if not r.ReadAppointments:
        problems.append("读不到 Tbl_CAH_Appointment")
    if not r.ReadView:
        problems.append("读不到 Qry_CAH_Appointment")
    warnings: list[str] = []
    if (r.ReadableObjects or 0) > READONLY_LOGIN_TABLES:
        warnings.append(f"读得到 {r.ReadableObjects} 个表或视图（只需要 {READONLY_LOGIN_TABLES} 个）")
    return problems, warnings


def missing_columns(found: set[tuple[str, str]]) -> list[str]:
    """found = {(表, 栏位)}；比较时不分大小写（SQL Server 也不分）。"""
    have = {(t.lower(), c.lower()) for t, c in found}
    return [f"{t}.{c}" for t, cols in REQUIRED_COLUMNS.items() for c in cols if (t.lower(), c.lower()) not in have]


class AppointmentSource(Protocol):
    def appointments_for(self, day: date, doctor_id: str) -> list[GpisAppointment]: ...


class WrongDatabaseError(RuntimeError):
    pass


class NotReadOnlyError(WrongDatabaseError):
    """读主机的 GPiS，但帐号不是只读的（例：用了 sa）。"""


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
            if self.is_production:
                problems, _ = permission_problems(cur.execute(PERMISSIONS_SQL).fetchone())
                if problems:
                    raise NotReadOnlyError(
                        "读主机的 GPiS 要用只读帐号（D52）。现在的帐号：" + "；".join(problems) + "。为了安全，拒绝读取。"
                    )
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

    def permissions(self):
        """连接用的帐号能做什么（给 --check-gpis 用）。回传一行：LoginName、IsSysadmin 等。"""
        return self._query(PERMISSIONS_SQL)[0]
