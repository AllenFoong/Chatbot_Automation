"""API 测试：用假的 GPiS 资料、固定的诊所设置代替数据库。"""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.availability import GpisAppointment
from app.db.rules import RulesNotConfigured
from app.db.session import get_session
from app.gpis import WrongDatabaseError, ensure_expected_database
from app.main import app, get_appointment_source, get_rules
from tests.rules import RULES

import pytest

SECRET_REMARK = "TEST PATIENT NAME 1 HOUR"
PARAMS = {"date": "2026-09-02", "doctor": "PHANG", "service": "S+P"}


class FakeSource:
    def __init__(self, rows=(), error=None):
        self.rows, self.error, self.calls = list(rows), error, []

    def appointments_for(self, day: date, doctor_id: str):
        self.calls.append((day, doctor_id))
        if self.error:
            raise self.error
        return self.rows


@pytest.fixture
def client():
    app.dependency_overrides[get_rules] = lambda: RULES     # 不连 PostgreSQL
    yield TestClient(app)
    app.dependency_overrides.clear()


def use(source):
    app.dependency_overrides[get_appointment_source] = lambda: source
    return source


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_availability_lists_open_slots(client):
    src = use(FakeSource([GpisAppointment(1, "16:00", "Booked", 1, SECRET_REMARK)]))
    r = client.get("/availability", params={"date": "2026-09-02", "doctor": "PHANG", "service": "S+P"})
    assert r.status_code == 200
    body = r.json()
    assert src.calls == [(date(2026, 9, 2), "PHANG")]
    assert body["day_status"] == "OK" and body["bookable"] is True
    assert body["patients"] == 1
    assert "16:00" not in body["available_30"] and "15:30" in body["available_30"]
    assert "15:30" not in body["available_60"]
    assert body["appointments"] is None


def test_response_never_contains_remarks(client):
    use(FakeSource([GpisAppointment(7, "16:00", "Booked", 1, SECRET_REMARK)]))
    r = client.get("/availability",
                   params={"date": "2026-09-02", "doctor": "PHANG", "service": "S+P", "debug": "true"})
    assert r.json()["appointments"][0]["appointment_id"] == 7
    assert "PATIENT" not in r.text and "NAME" not in r.text


def test_database_error_hides_details(client):
    use(FakeSource(error=RuntimeError("Server=secret;PWD=hunter2")))
    r = client.get("/availability", params={"date": "2026-09-02", "doctor": "PHANG", "service": "S+P"})
    assert r.status_code == 503
    assert "hunter2" not in r.text


def test_wrong_database_is_refused(client):
    with pytest.raises(WrongDatabaseError):
        ensure_expected_database("GPiS", "GPiS_Dev")
    ensure_expected_database("gpis_dev", "GPiS_Dev")

    use(FakeSource(error=WrongDatabaseError("连接到的数据库是 'GPiS'")))
    r = client.get("/availability", params={"date": "2026-09-02", "doctor": "PHANG", "service": "S+P"})
    assert r.status_code == 503


def test_bad_date_is_rejected(client):
    use(FakeSource())
    r = client.get("/availability", params={"date": "2026-02-30", "doctor": "PHANG", "service": "S+P"})
    assert r.status_code == 422


def use_settings_loader(monkeypatch, loader):
    """不用固定设置，改成走 get_rules → load_clinic_rules（换成假的）。"""
    del app.dependency_overrides[get_rules]
    app.dependency_overrides[get_session] = lambda: "fake session"
    monkeypatch.setattr("app.main.load_clinic_rules", loader)


def test_settings_come_from_database(client, monkeypatch):
    use(FakeSource())
    seen = []
    use_settings_loader(monkeypatch, lambda session: seen.append(session) or RULES)
    assert client.get("/availability", params=PARAMS).status_code == 200
    assert seen == ["fake session"]


@pytest.mark.parametrize("error,shown", [
    (RulesNotConfigured("数据库里还没有诊所设置：先执行 python -m app.db.seed"), "app.db.seed"),
    (OperationalError("SELECT 1", {}, Exception("password=hunter2")), "服务器日志"),
])
def test_settings_database_errors(client, monkeypatch, error, shown):
    use(FakeSource())

    def broken(session):
        raise error

    use_settings_loader(monkeypatch, broken)
    r = client.get("/availability", params=PARAMS)
    assert r.status_code == 503
    assert shown in r.json()["detail"]
    assert "hunter2" not in r.text
