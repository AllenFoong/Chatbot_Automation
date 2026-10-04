"""API 测试：用假的 GPiS 资料代替数据库。"""

from datetime import date

from fastapi.testclient import TestClient

from app.availability import GpisAppointment
from app.gpis import WrongDatabaseError, ensure_expected_database
from app.main import app, get_appointment_source

import pytest

SECRET_REMARK = "TEST PATIENT NAME 1 HOUR"


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
