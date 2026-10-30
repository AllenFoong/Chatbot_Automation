"""6b：AI 回复病人（全部是假名字、假号码；不连 Anthropic、不连 Meta：假的 Claude 照剧本回）。"""

from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app import ai_agent
from app.ai_agent import AFTER_HOURS, NOT_ALLOWED, reply
from app.config import AiSettings, get_ai_settings
from app.db import conversations as conv
from app.db.models import AppointmentRequest, Conversation, ConversationMode, Message, Sender, WaStatus
from app.db.seed import seed
from app.whatsapp import WhatsAppError
from tests.test_ai_tools import FakeGpis
from tests.test_ai_tools_patients import FAMILY, PHONE

NOW = datetime(2026, 10, 21, 2, 0, tzinfo=timezone.utc)         # 马来西亚 10:00，星期三
OPUS = AiSettings(model="claude-opus-5-5", effort="medium")


def text_block(t):
    return SimpleNamespace(type="text", text=t)


def tool_block(name, args, id_="t1"):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=args)


def response(*blocks, stop=None):
    stop = stop or ("tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn")
    return SimpleNamespace(stop_reason=stop, content=list(blocks),
                           usage=SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=0))


class FakeClaude:
    """script：每次呼叫回下一个（可以是 response，也可以是 function(kwargs) → response / raise）。"""

    def __init__(self, *script):
        self.script = list(script)
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        step = self.script.pop(0)
        return step(kwargs) if callable(step) else step


class FakeWhatsApp:
    def __init__(self, fail=None):
        self.sent: list[tuple[str, str]] = []
        self.fail = fail

    def send_text(self, to, body):
        if self.fail:
            raise self.fail
        self.sent.append((to, body))
        return f"wamid.ai{len(self.sent)}"


@pytest.fixture
def db(session, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ALLOWED_RECIPIENTS", PHONE)
    seed(session)
    return session


def incoming(db, body="我想洗牙", wamid="w1"):
    m, _ = conv.record_incoming_message(db, PHONE, body, wamid)
    db.commit()
    return m.conversation


def run(db, conversation, claude, whatsapp=None, now=NOW, settings=OPUS, gpis=None):
    return reply(db, conversation.id, client=claude, whatsapp=whatsapp or FakeWhatsApp(), gpis=gpis or FakeGpis(),
                 patients=FAMILY, now=now, settings=settings)


def bot_messages(db):
    return list(db.scalars(select(Message).where(Message.sender == Sender.BOT)))


# ---------- 一般的回复 ----------

def test_reply_is_sent_and_saved(db):
    c = incoming(db)
    claude, wa = FakeClaude(response(text_block("您好！请问是帮哪一位预约？"))), FakeWhatsApp()
    result = run(db, c, claude, wa)
    assert result.action == "replied"
    assert wa.sent == [(PHONE, "您好！请问是帮哪一位预约？")]
    [m] = bot_messages(db)
    assert (m.body, m.wa_message_id, m.wa_status) == ("您好！请问是帮哪一位预约？", "wamid.ai1", WaStatus.ACCEPTED)
    assert db.get(Conversation, c.id).mode == ConversationMode.BOT


def test_what_is_sent_to_claude(db):
    c = incoming(db)
    claude = FakeClaude(response(text_block("Hi")))
    run(db, c, claude)
    [call] = claude.calls
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"] == {"effort": "medium"}
    assert call["cache_control"] == {"type": "ephemeral"}
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert [t["name"] for t in call["tools"]] == ["find_patients", "get_treatment_doctor", "check_available_slots",
                                                  "find_next_available", "create_appointment_request",
                                                  "hand_over_to_human"]
    assert call["messages"] == [{"role": "user", "content": "我想洗牙"}]
    system = call["system"]
    assert "Today is 2026-10-21 (Wed), Malaysia time." in system
    assert "- S+P: Scaling & polishing" in system and "RCT:" not in system          # 只列 AI 能约的
    assert "Dr PHANG (code PHANG): Mon 09:00–17:00, break 12:00–13:00; Tue off" in system
    assert "never say you are a person" in system and "Never ask for an IC" in system


def test_cheaper_model_has_no_fallback(db):
    c = incoming(db)
    claude = FakeClaude(response(text_block("Hi")))
    run(db, c, claude, settings=AiSettings(model="claude-haiku-5-5", effort="low"))
    assert "fallbacks" not in claude.calls[0] and claude.calls[0]["output_config"] == {"effort": "low"}


def test_history_is_merged_and_starts_with_the_patient(db):
    c = incoming(db, "Hi", "w1")
    conv.record_outgoing_message(db, c, Sender.BOT, "Hello! How can I help?")
    incoming(db, "我想约", "w2")
    incoming(db, "明天", "w3")
    claude = FakeClaude(response(text_block("好的")))
    run(db, c, claude)
    assert claude.calls[0]["messages"] == [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello! How can I help?"},
        {"role": "user", "content": "我想约\n明天"},
    ]


# ---------- 工具 ----------

def test_booking_with_tools(db):
    c = incoming(db, "帮我儿子约 23/10 早上 10 点洗牙，PHANG 医生")
    claude = FakeClaude(
        response(tool_block("find_patients", {}, "t1")),
        response(tool_block("create_appointment_request",
                            {"service": "S+P", "doctor": "PHANG", "date": "2026-10-23", "time": "10:00",
                             "patient_id": "G502"}, "t2")),
        response(text_block("好的，已经帮 DEMO KID 记下 23/10 (Fri) 10:00 AM，员工确认后会通知您。")),
    )
    wa = FakeWhatsApp()
    result = run(db, c, claude, wa)
    assert result.action == "replied" and result.tools == ["find_patients", "create_appointment_request"]
    # 工具的结果送回给 Claude
    tool_result = claude.calls[1]["messages"][-1]["content"][0]
    assert tool_result["tool_use_id"] == "t1" and "G502" in tool_result["content"] and "is_error" not in tool_result
    [r] = db.scalars(select(AppointmentRequest)).all()
    assert (r.customer.name, r.service_code, r.doctor_id, str(r.preferred_date), r.conversation_id) == \
        ("DEMO KID", "S+P", "PHANG", "2026-10-23", c.id)
    assert len(wa.sent) == 1


def test_tool_error_goes_back_to_claude(db):
    c = incoming(db)
    claude = FakeClaude(
        response(tool_block("check_available_slots", {"date": "明天", "service": "S+P"})),
        response(text_block("请问是哪一天？")),
    )
    run(db, c, claude)
    tool_result = claude.calls[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True and "YYYY-MM-DD" in tool_result["content"]


def test_hand_over_sends_the_message_then_stops_the_ai(db):
    c = incoming(db, "牙齿很痛，脸肿了")
    claude = FakeClaude(
        response(tool_block("hand_over_to_human", {"reason": "Toothache with swelling", "urgent": True})),
        response(text_block("明白，我们的员工会尽快联系您。")),
    )
    wa = FakeWhatsApp()
    result = run(db, c, claude, wa)
    assert result.action == "handed_over" and result.reason == "URGENT: Toothache with swelling"
    assert wa.sent == [(PHONE, "明白，我们的员工会尽快联系您。")]
    c = db.get(Conversation, c.id)
    assert (c.mode, c.handover_reason) == (ConversationMode.HUMAN, "URGENT: Toothache with swelling")


# ---------- 不交给 AI 的情况 ----------

def test_number_not_in_allow_list_never_reaches_the_ai(db, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ALLOWED_RECIPIENTS", "60199999999")
    c = incoming(db)
    claude = FakeClaude()
    result = run(db, c, claude)
    assert (result.action, result.reason) == ("handed_over", NOT_ALLOWED)
    assert claude.calls == [] and db.get(Conversation, c.id).mode == ConversationMode.HUMAN


@pytest.mark.parametrize("hour_utc", [0, 13, 22])       # 马来西亚 8:00、21:00、6:00
def test_outside_ai_hours(db, hour_utc):
    c = incoming(db)
    claude = FakeClaude()
    result = run(db, c, claude, now=NOW.replace(hour=hour_utc))
    assert (result.action, result.reason) == ("handed_over", AFTER_HOURS) and claude.calls == []


def test_already_answered_or_reaction_is_skipped(db):
    c = incoming(db)
    conv.record_outgoing_message(db, c, Sender.BOT, "Hello")
    db.commit()
    assert run(db, c, FakeClaude()).reason == "already answered"
    incoming(db, "[Reaction 👍]", "w2")
    assert run(db, c, FakeClaude()).reason == "reaction"


def test_staff_conversation_is_skipped(db):
    c = incoming(db)
    conv.take_over(db, c, None)
    db.commit()
    assert run(db, c, FakeClaude()).action == "skipped"


# ---------- 出问题就转员工，不乱回 ----------

def test_api_error_hands_over(db):
    c = incoming(db)

    def boom(_):
        raise RuntimeError("401 invalid x-api-key sk-ant-secret")

    wa = FakeWhatsApp()
    result = run(db, c, FakeClaude(boom), wa)
    assert result.reason == "The AI could not reply (RuntimeError). Please reply to the patient."
    assert "secret" not in result.reason and wa.sent == []


@pytest.mark.parametrize(("stop", "why"), [("refusal", "the AI declined"), ("max_tokens", "reply too long")])
def test_refusal_or_cut_off_hands_over(db, stop, why):
    c = incoming(db)
    result = run(db, c, FakeClaude(response(text_block("..."), stop=stop)))
    assert why in result.reason and bot_messages(db) == []


def test_too_many_steps_hands_over(db):
    c = incoming(db)
    claude = FakeClaude(*[response(tool_block("find_patients", {}, f"t{i}")) for i in range(ai_agent.MAX_STEPS)])
    assert "too many steps" in run(db, c, claude).reason


def test_empty_reply_hands_over(db):
    c = incoming(db)
    assert "empty reply" in run(db, c, FakeClaude(response())).reason


def test_staff_takes_over_while_the_ai_is_thinking(db):
    c = incoming(db)

    def staff_replies(_):
        conv.take_over(db, db.get(Conversation, c.id), None)
        db.commit()
        return response(text_block("Hi"))

    wa = FakeWhatsApp()
    result = run(db, c, FakeClaude(staff_replies), wa)
    assert result.action == "skipped" and wa.sent == []


def test_whatsapp_failure_hands_over(db):
    c = incoming(db)
    result = run(db, c, FakeClaude(response(text_block("Hi"))), FakeWhatsApp(fail=WhatsAppError("code 131047")))
    assert result.reason == "The AI reply was not sent (code 131047). Please reply to the patient."
    assert bot_messages(db) == []


# ---------- 背景执行、设定 ----------

def test_background_run_takes_the_lock_and_replies(db):
    c = incoming(db)
    wa = FakeWhatsApp()
    result = ai_agent.reply_in_background(
        c.id, session_factory=lambda: nullcontext(db), client=FakeClaude(response(text_block("Hi"))),
        whatsapp=wa, gpis=FakeGpis(), patients=FAMILY,
    )
    # 现在的时间不一定在 9:00–21:00：回了或转员工都可以，只要没出错
    assert result is not None and result.action in ("replied", "handed_over")


def test_background_error_hands_over(db, monkeypatch):
    c = incoming(db)
    monkeypatch.setattr(ai_agent, "reply", lambda *a, **k: 1 / 0)
    assert ai_agent.reply_in_background(c.id, session_factory=lambda: nullcontext(db), client=FakeClaude(),
                                        whatsapp=FakeWhatsApp(), gpis=FakeGpis()) is None
    c = db.get(Conversation, c.id)
    assert c.mode == ConversationMode.HUMAN and "(error)" in c.handover_reason


def test_ai_settings(monkeypatch):
    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.delenv("AI_EFFORT", raising=False)
    assert get_ai_settings() == AiSettings("claude-opus-5-5", "medium")
    monkeypatch.setenv("AI_MODEL", "claude-haiku-5-5")
    monkeypatch.setenv("AI_EFFORT", "LOW")
    assert get_ai_settings() == AiSettings("claude-haiku-5-5", "low")
    monkeypatch.setenv("AI_EFFORT", "turbo")
    with pytest.raises(RuntimeError):
        get_ai_settings()
