"""手机号标准化：WhatsApp 的号码和员工输入、GPiS 里的号码，要转成同一种格式才能比对。

格式：国际格式、只有数字，例 60123456789（马来西亚）、6591234567（新加坡）。
规则来源：docs/gpis-database.md「手机号标准化规则」（统计 B10、C6）。
"""

from __future__ import annotations

import re

_NON_DIGIT = re.compile(r"\D")


def normalize_phone(raw: str | None) -> str | None:
    """转成国际格式；看不懂的回传 None（当作新病人，由员工确认）。"""
    s = (raw or "").strip()
    digits = _NON_DIGIT.sub("", s)
    if not digits:
        return None
    if digits.startswith("0"):                      # 本地号码：012-345 6789 → 60123456789
        result = "60" + digits[1:]
        return result if 10 <= len(result) <= 12 else None
    if s.startswith("+"):                           # 本来就写了国家码：+65 9123 4567
        return digits if 8 <= len(digits) <= 15 else None
    if len(digits) == 8 and digits[0] in "89":      # 新加坡号码没写国家码
        return "65" + digits
    if 10 <= len(digits) <= 12:                     # 已经有国家码：60…、65…（WhatsApp 给的就是这种）
        return digits
    return None
