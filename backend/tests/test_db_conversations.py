"""WhatsApp 对话（全部是假号码、假消息）。"""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.db import conversations as conv
from app.db.models import Conversation, ConversationMode, Message, Sender, WaStatus
from tests.database import add_staff, assert_rejected

PHONE = "60123456789"


def receive(session, wa_message_id, body="Hi, I want to book scaling", phone=PHONE):
    return conv.record_incoming_message(session, phone, body, wa_message_id)


def senders(session, conversation):
    return session.scalars(
        select(Message.sender).where(Message.conversation_id == conversation.id).order_by(Message.id)
    ).all()


def test_first_message_opens_bot_conversation(session):
    msg, is_new = conv.record_incoming_message(session, "+60 12-345 6789", "Hi", "wamid.1", profile_name="Test")
    assert is_new and msg.sender == Sender.CUSTOMER
    assert msg.conversation.mode == ConversationMode.BOT
    assert msg.conversation.wa_contact.wa_phone == PHONE            # 统一成国际格式
    assert msg.conversation.wa_contact.profile_name == "Test"


def test_same_message_delivered_twice_is_saved_once(session):
    first, _ = receive(session, "wamid.1")
    again, is_new = receive(session, "wamid.1")
    assert not is_new and again.id == first.id
    assert session.scalar(select(func.count()).select_from(Message)) == 1


def test_one_open_conversation_per_number(session):
    a, _ = receive(session, "wamid.1")
    b, _ = receive(session, "wamid.2")
    other, _ = receive(session, "wamid.3", phone="6591234567")
    assert a.conversation_id == b.conversation_id
    assert other.conversation_id != a.conversation_id


def test_database_refuses_second_open_conversation(session):
    msg, _ = receive(session, "wamid.1")
    assert_rejected(session, Conversation(wa_contact_id=msg.conversation.wa_contact_id))


def test_two_requests_opening_the_same_conversation(session, monkeypatch):
    """另一个请求刚好先开了对话（这边还没看到）：不会出错，回传那一段。"""
    msg, _ = receive(session, "wamid.1")
    monkeypatch.setattr(conv, "get_open_conversation", lambda s, contact_id: None)
    assert conv.open_conversation(session, msg.conversation.wa_contact).id == msg.conversation_id


def test_after_closing_a_new_message_opens_a_new_conversation(session):
    a, _ = receive(session, "wamid.1")
    conv.close_conversation(session, a.conversation)
    assert a.conversation.closed_at is not None
    b, _ = receive(session, "wamid.2")
    assert b.conversation_id != a.conversation_id
    assert b.conversation.mode == ConversationMode.BOT


def test_bot_is_muted_after_staff_takes_over(session):
    msg, _ = receive(session, "wamid.1")
    c = msg.conversation
    amy = add_staff(session)
    conv.record_outgoing_message(session, c, Sender.BOT, "Hello! Which date do you prefer?")
    conv.take_over(session, c, amy)
    with pytest.raises(conv.BotMuted):
        conv.record_outgoing_message(session, c, Sender.BOT, "...")
    conv.record_outgoing_message(session, c, Sender.STAFF, "Hi, this is Amy.", staff=amy)
    conv.hand_back_to_bot(session, c)
    conv.record_outgoing_message(session, c, Sender.BOT, "Noted.")
    assert senders(session, c) == [Sender.CUSTOMER, Sender.BOT, Sender.STAFF, Sender.BOT]


def test_staff_reply_takes_over_from_bot(session):
    msg, _ = receive(session, "wamid.1")
    amy = add_staff(session)
    conv.record_outgoing_message(session, msg.conversation, Sender.STAFF, "Hi", staff=amy)
    assert msg.conversation.mode == ConversationMode.HUMAN
    assert msg.conversation.assigned_staff_id == amy.id


def test_reply_from_phone_app_has_no_staff(session):
    msg, _ = receive(session, "wamid.1")
    out = conv.record_outgoing_message(session, msg.conversation, Sender.STAFF, "Hi", wa_message_id="wamid.out1")
    assert out.staff_id is None
    assert msg.conversation.mode == ConversationMode.HUMAN


def test_ai_hands_over_with_reason(session):
    msg, _ = receive(session, "wamid.1")
    conv.hand_over_to_human(session, msg.conversation, "病人要求真人")
    assert msg.conversation.mode == ConversationMode.HUMAN
    assert msg.conversation.handover_reason == "病人要求真人"
    with pytest.raises(conv.BotMuted):
        conv.record_outgoing_message(session, msg.conversation, Sender.BOT, "...")


def test_closed_conversation_rejects_messages(session):
    msg, _ = receive(session, "wamid.1")
    conv.close_conversation(session, msg.conversation)
    for sender in (Sender.BOT, Sender.STAFF):
        with pytest.raises(conv.ConversationClosed):
            conv.record_outgoing_message(session, msg.conversation, sender, "Hi")


def test_bad_number_and_wrong_sender(session):
    with pytest.raises(ValueError):
        receive(session, "wamid.1", phone="12345")
    msg, _ = receive(session, "wamid.2")
    with pytest.raises(ValueError):
        conv.record_outgoing_message(session, msg.conversation, Sender.CUSTOMER, "Hi")
    with pytest.raises(ValueError):
        conv.record_outgoing_message(session, msg.conversation, Sender.BOT, "Hi", staff=add_staff(session))


def test_customer_service_window(session):
    msg, _ = receive(session, "wamid.1")
    contact_id = msg.conversation.wa_contact_id
    t = msg.created_at
    assert conv.customer_service_window_open(session, contact_id, now=t + timedelta(hours=23))
    assert not conv.customer_service_window_open(session, contact_id, now=t + timedelta(hours=25))

    # AI 的回复不会延长 24 小时
    reply = conv.record_outgoing_message(session, msg.conversation, Sender.BOT, "Hello")
    reply.created_at = t + timedelta(hours=20)
    session.flush()
    assert not conv.customer_service_window_open(session, contact_id, now=t + timedelta(hours=25))

    # 从来没收到消息的号码：不能发一般消息
    other = conv.get_or_create_wa_contact(session, "6591234567")
    assert not conv.customer_service_window_open(session, other.id)


def test_customer_service_window_ends_24_hours_after_last_patient_message(session):
    msg, _ = receive(session, "wamid.1")
    contact_id = msg.conversation.wa_contact_id
    assert conv.customer_service_window_ends_at(session, contact_id) == msg.created_at + timedelta(hours=24)
    assert conv.customer_service_window_ends_at(session, conv.get_or_create_wa_contact(session, "6591234567").id) \
        is None


def test_delivery_status_only_moves_forward(session):
    msg, _ = receive(session, "wamid.in")
    sent = conv.record_outgoing_message(session, msg.conversation, Sender.STAFF, "Hello",
                                        staff=add_staff(session), wa_message_id="wamid.out",
                                        wa_status=WaStatus.ACCEPTED)
    conv.update_message_status(session, "wamid.out", WaStatus.READ)
    conv.update_message_status(session, "wamid.out", WaStatus.DELIVERED)     # 比 read 晚到：不能退回去
    assert sent.wa_status == WaStatus.READ

    conv.update_message_status(session, "wamid.out", WaStatus.FAILED, "131047: Re-engagement message")
    conv.update_message_status(session, "wamid.out", WaStatus.SENT)          # 失败了就不会再变
    assert (sent.wa_status, sent.wa_error) == (WaStatus.FAILED, "131047: Re-engagement message")


def test_delivery_status_ignores_unknown_and_incoming_messages(session):
    msg, _ = receive(session, "wamid.in")
    assert conv.update_message_status(session, "wamid.unknown", WaStatus.SENT) is None
    assert conv.update_message_status(session, "wamid.in", WaStatus.READ) is None
    assert msg.wa_status is None


def test_database_rules_for_delivery_status(session):
    msg, _ = receive(session, "wamid.in")
    c = msg.conversation
    # 病人发来的消息没有送达状态；只有 FAILED 才有错误原因
    assert_rejected(session, Message(conversation_id=c.id, sender=Sender.CUSTOMER, body="x", wa_status=WaStatus.SENT))
    assert_rejected(session, Message(conversation_id=c.id, sender=Sender.BOT, body="x", wa_status=WaStatus.SENT,
                                     wa_error="oops"))
