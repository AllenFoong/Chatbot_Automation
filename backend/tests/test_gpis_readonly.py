"""只读帐号（D52）：读主机的 GPiS 时，帐号不是只读的就拒绝。不连真的 SQL Server（假的 pyodbc）。"""

import sys
import types
from collections import namedtuple

import pytest

from app import reminders_cli
from app.gpis import PERMISSIONS_SQL, GpisReader, NotReadOnlyError, permission_problems

Perms = namedtuple("Perms", "LoginName IsSysadmin ReadAppointments ReadView ReadUsers ChangeDatabase "
                            "WritableObjects ExecutableProcedures ReadableObjects")
READER = Perms("chatbot_reader", 0, 1, 1, None, 0, 0, 0, 2)
SA = Perms("sa", 1, 1, 1, 1, 2, 120, 40, 120)


def test_readonly_login_has_no_problems():
    assert permission_problems(READER) == ([], [])


def test_sa_is_not_readonly():
    problems, _ = permission_problems(SA)
    assert problems[0] == "sa 是 sysadmin，什么都能改"
    assert "读得到 Tbl_User（D52：不能给）" in problems and len(problems) == 5


@pytest.mark.parametrize("change, problem", [
    (dict(WritableObjects=1), "可以写入 1 个表或视图"),
    (dict(ExecutableProcedures=3), "可以执行 3 个 stored procedure（可能会写入）"),
    (dict(ChangeDatabase=1), "可以改数据库的结构"),
    (dict(ReadUsers=1), "读得到 Tbl_User（D52：不能给）"),
    (dict(ReadView=None), "读不到 Qry_CAH_Appointment"),
    (dict(ReadAppointments=0), "读不到 Tbl_CAH_Appointment"),
])
def test_each_problem(change, problem):
    assert permission_problems(READER._replace(**change))[0] == [problem]


def test_extra_tables_are_only_a_warning():
    assert permission_problems(READER._replace(ReadableObjects=5)) == (
        [], ["读得到 5 个表或视图（只需要 2 个）"])


class FakeCursor:
    def __init__(self, db, perms, log):
        self.db, self.perms, self.log, self.last = db, perms, log, None

    def execute(self, sql, *params):
        self.log.append(sql)
        self.last = sql
        return self

    def fetchval(self):
        return self.db

    def fetchone(self):
        return self.perms

    def fetchall(self):
        return [self.perms] if self.last == PERMISSIONS_SQL else ["row"]


@pytest.fixture
def fake_pyodbc(monkeypatch):
    log: list[str] = []
    state = {"db": "GPiS", "perms": READER}

    def connect(*args, **kwargs):
        cur = FakeCursor(state["db"], state["perms"], log)
        return types.SimpleNamespace(cursor=lambda: cur, close=lambda: None)

    monkeypatch.setitem(sys.modules, "pyodbc", types.SimpleNamespace(connect=connect))
    return state, log


def test_production_with_readonly_login_reads(fake_pyodbc):
    _, log = fake_pyodbc
    assert GpisReader("x", "GPiS")._query("SELECT 1") == ["row"]
    assert log == ["SELECT DB_NAME()", PERMISSIONS_SQL, "SELECT 1"]


def test_production_with_sa_is_refused(fake_pyodbc):
    state, log = fake_pyodbc
    state["perms"] = SA
    with pytest.raises(NotReadOnlyError, match="sa 是 sysadmin"):
        GpisReader("x", "GPiS")._query("SELECT 1")
    assert "SELECT 1" not in log            # 预约一条都没有读


def test_dev_database_does_not_check_the_login(fake_pyodbc):
    state, log = fake_pyodbc
    state.update(db="GPiS_Dev", perms=SA)    # 开发电脑用 Windows 帐号（sysadmin）连 GPiS_Dev
    assert GpisReader("x", "GPiS_Dev")._query("SELECT 1") == ["row"]
    assert PERMISSIONS_SQL not in log


class FakeReader(GpisReader):
    def __init__(self, database, perms=READER, missing=()):
        super().__init__("x", database)
        self._perms, self._missing = perms, list(missing)

    def missing_columns(self):
        return self._missing

    def permissions(self):
        if self.is_production and permission_problems(self._perms)[0]:
            raise NotReadOnlyError("读主机的 GPiS 要用只读帐号（D52）")
        return self._perms


@pytest.mark.parametrize("reader, code, expected", [
    (FakeReader("GPiS"), 0, "[OK] 帐号 chatbot_reader 是只读的"),
    (FakeReader("GPiS", perms=SA), 1, "UID=chatbot_reader"),
    (FakeReader("GPiS_Dev", perms=SA), 0, "开发电脑用 Windows 帐号"),
    (FakeReader("GPiS_Dev", perms=READER._replace(ReadableObjects=4)), 0, "[提醒] 读得到 4 个表或视图"),
    (FakeReader("GPiS_Dev", missing=["Qry_CAH_Appointment.HPNo"]), 1, "Qry_CAH_Appointment.HPNo"),
])
def test_check_gpis_output(monkeypatch, capsys, reader, code, expected):
    monkeypatch.setattr(reminders_cli, "get_reminder_source", lambda: reader)
    assert reminders_cli.check_gpis() == code
    assert expected in capsys.readouterr().out
