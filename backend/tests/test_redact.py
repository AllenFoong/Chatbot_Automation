"""病人传的 IC / 护照号码：存之前遮掉后面 6 位（D69）。全部是假号码。"""

import pytest

from app.redact import mask_id_numbers


@pytest.mark.parametrize("text,expected", [
    # 马来西亚 IC：留前面 6 位（生日），- 和空格照留
    ("900101-01-1234", "900101-**-****"),
    ("900101011234", "900101******"),
    ("900101 01 1234", "900101 ** ****"),
    ("我的IC是 900101-01-1234，要约明天", "我的IC是 900101-**-****，要约明天"),
    ("Saya 900101-01-1234 nak buat appointment", "Saya 900101-**-**** nak buat appointment"),
    # 新加坡 NRIC / FIN、护照：遮后面 6 个字
    ("S1234567A", "S12******"),
    ("t1234567z", "t12******"),
    ("passport A12345678 ok", "passport A12****** ok"),
    ("K1234567A", "K12******"),
    ("EA1234567", "EA1******"),
    # 有关键字：格式认不出来也遮
    ("IC: 9001010112", "IC: 9001******"),
    ("NRIC 900101011234", "NRIC 900101******"),
    ("MyKad no. 900101-01-1234", "MyKad no. 900101-**-****"),
    ("身份证 900101011234", "身份证 900101******"),
    ("护照号码 E 1234 5678", "护照号码 E 12** ****"),
    ("IC 900101 01 1234 thanks", "IC 900101 ** **** thanks"),
    ("KP: 900101-01-1234", "KP: 900101-**-****"),
    # 两个号码都遮
    ("900101-01-1234 & 950505-05-5555", "900101-**-**** & 950505-**-****"),
])
def test_masks_the_last_6(text, expected):
    assert mask_id_numbers(text) == expected


@pytest.mark.parametrize("text", [
    "Hi, can I book scaling?",
    "16/10 10:00 AM",
    "明天 2:30pm 可以吗",
    "SC 36 OR(P) S+P",
    "RCT (C) 36,SC 36 (P)",
    "ISSUE CROWN 46 (P) *C",
    "SCAN B 33-37 (P)",
    "call 012-345 6789",
    "60123456789",
    "clinic 123456",           # ic 在单字里面不算
    "ic 12345",                # 不到 6 个字
    "已经遮过 900101-**-****",  # 不会再遮生日
])
def test_leaves_other_text_alone(text):
    assert mask_id_numbers(text) == text


@pytest.mark.parametrize("text", [
    "IC 900101-01-1234, passport A12345678",
    "NRIC 900101 01 1234",
    "身份证 900101011234",
    "S1234567A",
])
def test_masking_twice_changes_nothing(text):
    """存的时候遮一次、送去 AI 前可能再遮一次：生日不能被遮掉。"""
    once = mask_id_numbers(text)
    assert mask_id_numbers(once) == once
