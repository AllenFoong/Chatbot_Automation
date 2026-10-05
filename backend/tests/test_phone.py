"""手机号标准化（全部是假号码）。规则：docs/gpis-database.md「手机号标准化规则」。"""

import pytest

from app.phone import normalize_phone


@pytest.mark.parametrize("raw,expected", [
    ("012-345 6789", "60123456789"),
    ("0123456789", "60123456789"),
    (" 016-1234567", "60161234567"),        # 前面有空格（统计 C6）
    ("011-2345 6789", "601123456789"),      # 11 位的手机号
    ("07-123 4567", "6071234567"),          # Johor 座机
    (":0123456789", "60123456789"),         # 打错的符号
    ("+60 12-345 6789", "60123456789"),
    ("+65 9123 4567", "6591234567"),
    ("+44 20 7946 0000", "442079460000"),
    ("60123456789", "60123456789"),         # WhatsApp 给的格式
    ("6591234567", "6591234567"),           # 已经有国家码，只是没写 +
    ("9123 4567", "6591234567"),            # 新加坡号码没写国家码
    ("8123-4567", "6581234567"),
])
def test_normalize(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "-", "0", "12345", "7123 4567", "+12", "012-34"])
def test_cannot_normalize(raw):
    assert normalize_phone(raw) is None
