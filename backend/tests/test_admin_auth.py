"""Admin Platform：登录、权限、员工账号（全部假资料）。"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.auth import COOKIE_NAME
from app.db.models import StaffRole, StaffSession
from tests.database import PASSWORD, add_staff


def test_login_sets_httponly_cookie_and_me_works(session, client_for):
    add_staff(session, "amy", password=PASSWORD)
    client = client_for()
    r = client.post("/api/auth/login", json={"username": " AMY ", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["username"] == "amy"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/auth/me").json()["role"] == "STAFF"
    # 数据库只存 token 的 hash，不存 token 本身
    token_hash = session.scalars(select(StaffSession.token_hash)).one()
    assert token_hash != client.cookies[COOKIE_NAME] and len(token_hash) == 64


@pytest.mark.parametrize("username,password", [("amy", "wrong-password"), ("nobody", PASSWORD)])
def test_wrong_login_gives_the_same_message(session, client_for, username, password):
    add_staff(session, "amy", password=PASSWORD)
    r = client_for().post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 401 and r.json()["detail"] == "Wrong username or password"


def test_everything_needs_login(session, client_for):
    client = client_for()
    for path in ("/api/auth/me", "/api/conversations", "/api/requests", "/api/doctors", "/api/staff"):
        assert client.get(path).status_code == 401, path


def test_api_responses_are_not_cached(session, client_for):
    """/api 的回应有病人名字、号码：浏览器不能存进硬盘的快取（A10、D67）。"""
    add_staff(session, "amy", password=PASSWORD)
    client = client_for("amy")
    assert client.get("/api/auth/me").headers["cache-control"] == "no-store"
    assert client_for().get("/api/conversations").headers["cache-control"] == "no-store"   # 401 也一样
    assert "cache-control" not in client.get("/health").headers


def test_logout_ends_the_session(session, client_for):
    add_staff(session, "amy", password=PASSWORD)
    client = client_for("amy")
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_expired_session_is_refused(session, client_for):
    add_staff(session, "amy", password=PASSWORD)
    client = client_for("amy")
    for s in session.scalars(select(StaffSession)):
        s.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.flush()
    assert client.get("/api/auth/me").status_code == 401


def test_deactivated_staff_is_locked_out_at_once(session, client_for):
    add_staff(session, "boss", role=StaffRole.ADMIN, password=PASSWORD)
    amy = add_staff(session, "amy", password=PASSWORD)
    amy_client = client_for("amy")
    r = client_for("boss").patch(f"/api/staff/{amy.id}", json={"active": False})
    assert r.status_code == 200
    assert amy_client.get("/api/auth/me").status_code == 401
    assert client_for().post("/api/auth/login", json={"username": "amy", "password": PASSWORD}).status_code == 401


def test_staff_cannot_change_settings_or_accounts(session, client_for):
    add_staff(session, "amy", password=PASSWORD)
    client = client_for("amy")
    assert client.get("/api/doctors").status_code == 200          # 看可以
    assert client.patch("/api/settings", json={"max_per_slot_for_ai": 2}).status_code == 403
    assert client.post("/api/closures", json={"closure_date": "2026-12-25", "reason": "X"}).status_code == 403
    assert client.get("/api/staff").status_code == 403


def test_change_own_password_logs_out_other_devices(session, client_for):
    add_staff(session, "amy", password=PASSWORD)
    laptop, phone = client_for("amy"), client_for("amy")
    r = laptop.post("/api/auth/password", json={"current_password": "wrong", "new_password": "new-password-1"})
    assert r.status_code == 400
    r = laptop.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": "short"})
    assert r.status_code == 422
    r = laptop.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": "new-password-1"})
    assert r.status_code == 204
    assert laptop.get("/api/auth/me").status_code == 200        # 改密码的这台还在
    assert phone.get("/api/auth/me").status_code == 401         # 另一台要重新登录
    client_for("amy", password="new-password-1")


def test_admin_manages_staff_accounts(session, client_for):
    add_staff(session, "boss", role=StaffRole.ADMIN, password=PASSWORD)
    boss = client_for("boss")
    r = boss.post("/api/staff", json={"username": "Ben", "name": "Ben (test)", "password": "ben-password-1"})
    assert r.status_code == 201 and r.json()["username"] == "ben" and r.json()["role"] == "STAFF"
    assert boss.post("/api/staff", json={"username": "ben", "name": "x", "password": "ben-password-1"}).status_code == 409
    assert boss.post("/api/staff", json={"username": "cat", "name": "x", "password": "short"}).status_code == 422

    ben_id = r.json()["id"]
    ben = client_for("ben", password="ben-password-1")
    assert boss.patch(f"/api/staff/{ben_id}", json={"password": "reset-password-1"}).status_code == 200
    assert ben.get("/api/auth/me").status_code == 401          # 重设密码后要重新登录
    client_for("ben", password="reset-password-1")


def test_last_admin_cannot_be_removed(session, client_for):
    boss = add_staff(session, "boss", role=StaffRole.ADMIN, password=PASSWORD)
    client = client_for("boss")
    for change in ({"role": "STAFF"}, {"active": False}):
        r = client.patch(f"/api/staff/{boss.id}", json=change)
        assert r.status_code == 409 and "admin" in r.json()["detail"]
    other = add_staff(session, "boss2", role=StaffRole.ADMIN, password=PASSWORD)
    assert client.patch(f"/api/staff/{other.id}", json={"role": "STAFF"}).status_code == 200


def test_delete_an_unused_account(session, client_for):
    """建错、重复的账号可以删掉；它登录中的 session 也一起没了（D75）。"""
    add_staff(session, "boss", role=StaffRole.ADMIN, password=PASSWORD)
    extra = add_staff(session, "typo", password=PASSWORD)
    boss, typo = client_for("boss"), client_for("typo")
    assert typo.get("/api/auth/me").status_code == 200
    assert typo.delete(f"/api/staff/{extra.id}").status_code == 403             # STAFF 不能删
    assert boss.delete(f"/api/staff/{extra.id}").status_code == 204
    assert [m["username"] for m in boss.get("/api/staff").json()] == ["boss"]
    assert typo.get("/api/auth/me").status_code == 401
    assert session.scalars(select(StaffSession).where(StaffSession.staff_id == extra.id)).all() == []
    assert boss.delete(f"/api/staff/{extra.id}").status_code == 404


def test_used_accounts_and_yourself_cannot_be_deleted(session, client_for):
    from app.db import conversations as conv
    from app.db.models import Sender

    boss_row = add_staff(session, "boss", role=StaffRole.ADMIN, password=PASSWORD)
    amy = add_staff(session, "amy", password=PASSWORD)
    boss = client_for("boss")
    msg, _ = conv.record_incoming_message(session, "60120000001", "hi", "wamid.del.1")
    conv.record_outgoing_message(session, msg.conversation, Sender.STAFF, "hello", staff=amy)
    r = boss.delete(f"/api/staff/{amy.id}")
    assert r.status_code == 409
    assert "sent messages" in r.json()["detail"] and "Deactivate" in r.json()["detail"]
    r = boss.delete(f"/api/staff/{boss_row.id}")
    assert r.status_code == 409 and "your own account" in r.json()["detail"]
    assert len(boss.get("/api/staff").json()) == 2
