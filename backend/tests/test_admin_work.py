"""Admin Platform：对话和预约请求（用 app/db/demo.py 的假资料）。"""

from datetime import date

import pytest

from app.db.demo import add_demo_data
from app.db.seed import seed
from tests.database import PASSWORD, add_staff

TODAY = date(2026, 10, 5)     # 星期一 → 下一个星期五是 10-09


@pytest.fixture
def amy(session, client_for):
    seed(session)
    add_demo_data(session, TODAY)
    add_staff(session, "amy", password=PASSWORD)
    return client_for("amy")


def test_open_conversations_newest_first(amy):
    rows = amy.get("/api/conversations").json()
    assert [c["profile_name"] for c in rows] == ["Demo SG", "Demo Patient", "Demo Mum"]   # 结束的不列出
    mum = rows[2]
    assert mum["wa_phone"] == "60120000001" and mum["mode"] == "BOT"
    assert mum["last_message_sender"] == "BOT" and mum["last_message_preview"].startswith("Noted")
    assert rows[0]["mode"] == "HUMAN" and "human" in rows[0]["handover_reason"]
    assert [c["profile_name"] for c in amy.get("/api/conversations", params={"mode": "CLOSED"}).json()] \
        == ["Demo Cancel"]


def test_conversation_detail_has_all_messages(amy):
    mum_id = amy.get("/api/conversations").json()[2]["id"]
    detail = amy.get(f"/api/conversations/{mum_id}").json()
    assert [m["sender"] for m in detail["messages"]] == ["CUSTOMER", "BOT", "CUSTOMER", "BOT"]
    assert amy.get("/api/conversations/999999").status_code == 404


def test_take_over_hand_back_and_close(amy):
    mum_id = amy.get("/api/conversations").json()[2]["id"]
    r = amy.post(f"/api/conversations/{mum_id}/take-over").json()
    assert r["mode"] == "HUMAN" and r["assigned_staff_name"] == "amy (test)"
    r = amy.post(f"/api/conversations/{mum_id}/hand-back").json()
    assert r["mode"] == "BOT" and r["assigned_staff_id"] is None
    r = amy.post(f"/api/conversations/{mum_id}/close").json()
    assert r["mode"] == "CLOSED" and r["closed_at"] is not None
    assert amy.post(f"/api/conversations/{mum_id}/take-over").status_code == 409


def test_pending_requests_oldest_first(amy):
    rows = amy.get("/api/requests").json()
    assert [(r["customer_name"], r["service_code"]) for r in rows] == [
        ("Demo Kid A", "S+P"), ("Demo Kid B", "S+P"), ("Demo Patient", "OR")]
    kid_a, kid_b = rows[0], rows[1]
    assert kid_a["group_id"] == kid_b["group_id"] is not None          # 两个孩子一起来
    assert kid_a["preferred_date"] == "2026-10-09" and kid_a["preferred_slot"] == "16:00:00"
    assert kid_a["service_name"] == "Scaling & polishing" and kid_a["customer_phone"] == "60120000001"
    assert [r["customer_name"] for r in amy.get("/api/requests", params={"status": "CANCELLED"}).json()] \
        == ["Demo Cancel"]


def test_confirm_reject_and_invalid_change(amy):
    kid_a, kid_b, _ = amy.get("/api/requests").json()
    r = amy.post(f"/api/requests/{kid_a['id']}/confirm", json={"gpis_appointment_id": 123456})
    assert r.status_code == 200
    assert r.json()["status"] == "CONFIRMED" and r.json()["gpis_appointment_id"] == 123456
    assert r.json()["handled_at"] is not None
    assert amy.post(f"/api/requests/{kid_b['id']}/confirm").json()["gpis_appointment_id"] is None   # 可以不填
    assert amy.post(f"/api/requests/{kid_a['id']}/reject").status_code == 409     # 已确认不能再拒绝
    assert amy.post(f"/api/requests/{kid_a['id']}/cancel").json()["status"] == "CANCELLED"
    assert amy.post("/api/requests/999999/reject").status_code == 404
    assert [r["customer_name"] for r in amy.get("/api/requests").json()] == ["Demo Patient"]
