"""Admin Platform：设置（全部假资料）。改了设置，空档计算马上用新的设置。"""

from datetime import date

import pytest

from app.availability import check_available_slots
from app.db.models import StaffRole
from app.db.rules import load_clinic_rules
from app.db.seed import seed
from tests.database import PASSWORD, add_staff

WED = date(2026, 9, 2)
WORK = {"is_working": True, "start_time": "09:00", "last_slot": "16:30", "break_start": "12:00", "break_end": "13:00"}


@pytest.fixture
def boss(session, client_for):
    seed(session)
    add_staff(session, "boss", role=StaffRole.ADMIN, password=PASSWORD)
    return client_for("boss")


def test_new_doctor_starts_with_all_days_off(boss, session):
    r = boss.post("/api/doctors", json={"id": "lee", "display_name": "LEE", "remark_tag": "L"})
    assert r.status_code == 201 and r.json()["id"] == "LEE"
    days = boss.get("/api/doctors/LEE/schedule").json()
    assert [d["weekday"] for d in days] == list(range(1, 8)) and not any(d["is_working"] for d in days)
    assert boss.post("/api/doctors", json={"id": "LEE", "display_name": "again"}).status_code == 409


def test_schedule_change_takes_effect(boss, session):
    week = [{"weekday": wd, **WORK} for wd in range(1, 8)]          # GOH 改成每天都上班
    r = boss.put("/api/doctors/goh/schedule", json=week)
    assert r.status_code == 200 and all(d["is_working"] for d in r.json())
    result = check_available_slots(WED, "GOH", "S+P", [], load_clinic_rules(session))
    assert result.day_status == "OK"                                   # 原本星期三休息


@pytest.mark.parametrize("bad", [
    {"start_time": "09:15"},                                           # 不在 30 分钟的格上
    {"start_time": "17:00"},                                           # 开始比最后一格晚
    {"break_start": "13:00", "break_end": "12:00"},                    # 午休结束比开始早
])
def test_bad_schedule_is_rejected_and_nothing_changes(boss, session, bad):
    week = [{"weekday": wd, **WORK, **bad} for wd in range(1, 8)]
    r = boss.put("/api/doctors/PHANG/schedule", json=week)
    assert r.status_code == 422 and r.json()["rule"].startswith("ck_doctor_schedules")
    assert boss.get("/api/doctors/PHANG/schedule").json()[0]["start_time"] == "09:00:00"


def test_schedule_needs_all_seven_days(boss):
    r = boss.put("/api/doctors/PHANG/schedule", json=[{"weekday": 1, **WORK}])
    assert r.status_code == 422


def test_doctor_who_left_is_unknown(boss, session):
    assert boss.patch("/api/doctors/GOH", json={"active": False}).json()["active"] is False
    result = check_available_slots(date(2026, 9, 4), "GOH", "S+P", [], load_clinic_rules(session))
    assert result.day_status == "UNKNOWN_DOCTOR"
    assert boss.patch("/api/doctors/NOPE", json={"active": False}).status_code == 404


def test_services(boss, session):
    r = boss.patch("/api/services/C/UP", json={"can_be_third": True})      # 代码里有 /
    assert r.status_code == 200 and r.json()["can_be_third"] is True
    assert "C/UP" in load_clinic_rules(session).can_be_third
    r = boss.post("/api/services", json={"code": "bleach", "name": "Bleaching"})
    assert r.status_code == 201 and r.json()["code"] == "BLEACH" and r.json()["active"] is True
    assert boss.patch("/api/services/NOPE", json={"active": False}).status_code == 404


# 诊所给的 2026 年休息的假期（2026-10-11，D61）；New Year's Day 是 2027 年的名单才有的（W57），每年都加
CLINIC_2026 = {
    "2026-01-01": "New Year's Day",
    "2026-02-17": "Chinese New Year", "2026-02-18": "Chinese New Year Holiday",
    "2026-03-21": "Hari Raya Aidilfitri", "2026-03-22": "Hari Raya Aidilfitri Holiday",
    "2026-03-23": "Sultan of Johor's Birthday", "2026-05-01": "Labour Day", "2026-08-31": "Merdeka Day",
    "2026-09-16": "Malaysia Day", "2026-11-08": "Deepavali", "2026-12-25": "Christmas Day",
}


def test_import_only_the_holidays_the_clinic_closes(boss, session):
    r = boss.post("/api/closures/import-holidays", json={"year": 2026}).json()
    added = {c["closure_date"]: c["reason"] for c in r["added"]}
    assert added == CLINIC_2026                     # 和诊所的名单一模一样
    assert "2026-05-31" not in added                # Wesak：诊所照常营业
    assert "2026-11-09" not in added                # Deepavali 的替代假（observed）：不休
    assert "2026-03-24" not in added and "2026-03-20" not in added    # Hari Raya 的替代假、additional holiday
    assert r["already_there"] == 0


# 诊所给的 2027 年名单（2026-10-12，W57）。Deepavali（10 月 28 日）是诊所漏写的，照样休（W59）
CLINIC_2027 = {
    date(2027, 1, 1): "New Year's Day", date(2027, 2, 6): "Chinese New Year",
    date(2027, 2, 7): "Chinese New Year Holiday", date(2027, 3, 10): "Hari Raya Aidilfitri",
    date(2027, 3, 11): "Hari Raya Aidilfitri Holiday", date(2027, 3, 23): "Sultan of Johor's Birthday",
    date(2027, 5, 1): "Labour Day", date(2027, 8, 31): "Merdeka Day", date(2027, 9, 16): "Malaysia Day",
    date(2027, 12, 25): "Christmas Day",
}


def test_clinic_holidays_2027_matches_the_clinic_list():
    from app.api.settings import clinic_holidays
    found = clinic_holidays(2027)
    assert {d: n for d, n in found.items() if d in CLINIC_2027} == CLINIC_2027    # 诊所名单上的每一天都有
    assert set(found) - set(CLINIC_2027) == {date(2027, 10, 28)}                 # 加上漏写的 Deepavali（W59）
    assert date(2027, 2, 9) not in found        # 农历新年在星期日的替代假：不休（W56）


def test_import_holidays_then_add_own_closure(boss, session):
    r = boss.post("/api/closures/import-holidays", json={"year": 2026}).json()
    added = {c["closure_date"]: c["reason"] for c in r["added"]}
    assert r["already_there"] == 0
    again = boss.post("/api/closures/import-holidays", json={"year": 2026}).json()
    assert again["added"] == [] and again["already_there"] == len(added)    # 再导入一次不会重复

    # 农历新年诊所多休的一天（套件里没有，员工自己加）；已经是假期的日子不能重复加
    r = boss.post("/api/closures", json={"closure_date": "2026-02-16", "reason": "CNY eve, clinic closed"})
    assert r.status_code == 201
    r = boss.post("/api/closures", json={"closure_date": "2026-02-17", "reason": "again"})
    assert r.status_code == 409 and r.json()["rule"] == "pk_clinic_closures"
    rules = load_clinic_rules(session)
    assert check_available_slots(date(2026, 12, 25), "PHANG", "S+P", [], rules).day_status == "CLINIC_CLOSED"
    assert len(boss.get("/api/closures", params={"year": 2026}).json()) == len(added) + 1
    assert boss.delete("/api/closures/2026-12-25").status_code == 204
    assert boss.delete("/api/closures/2026-12-25").status_code == 404


def test_doctor_leave(boss, session):
    r = boss.post("/api/leaves", json={"doctor_id": "goh", "leave_date": "2026-10-10", "reason": "Conference"})
    assert r.status_code == 201 and r.json()["doctor_id"] == "GOH"
    rules = load_clinic_rules(session)
    assert check_available_slots(date(2026, 10, 10), "GOH", "S+P", [], rules).day_status == "DOCTOR_ON_LEAVE"
    assert [x["leave_date"] for x in boss.get("/api/leaves", params={"from_date": "2026-10-01"}).json()] \
        == ["2026-10-10"]
    assert boss.delete("/api/leaves/GOH/2026-10-10").status_code == 204
    assert boss.post("/api/leaves", json={"doctor_id": "NOPE", "leave_date": "2026-10-10"}).status_code == 404


def test_clinic_settings(boss, session):
    assert boss.get("/api/settings").json() == {"max_per_slot": 3, "max_per_slot_for_ai": 3, "clinic_contact_id": 34094}
    assert boss.patch("/api/settings", json={"max_per_slot_for_ai": 2}).json()["max_per_slot_for_ai"] == 2
    assert load_clinic_rules(session).max_per_slot_for_ai == 2
    r = boss.patch("/api/settings", json={"max_per_slot": 5})                # 每格最多 3 人（W22）
    assert r.status_code == 422 and r.json()["rule"] == "ck_clinic_settings_max_per_slot"
