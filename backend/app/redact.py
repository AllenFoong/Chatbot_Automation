"""病人传来的 IC / 护照号码：存进数据库、送去 AI 之前先遮掉后面 6 位（D69，docs/architecture.md 11.7）。

- 马来西亚 IC（12 位数字，中间可以有 - 或空格）：留前面 6 位（生日），例 900101-01-1234 → 900101-**-****
- 新加坡 NRIC / FIN（S T F G M + 7 位数字 + 字母）、护照（1–2 个英文字母 + 6–8 位数字 + 可能一个字母）：
  遮后面 6 个字，例 S1234567A → S12******
- 前面有 IC、NRIC、MyKad、passport、护照、身份证、KP 的号码：上面的格式认不出来也遮后面 6 个字
- 宁可多遮：一个 12 位的电话号码被遮了后面 6 位也没关系。日期、时间、牙位、疗程代码不会被遮
"""

from __future__ import annotations

import re

MASK = "*"

# 前后不能紧接着英文字母或数字（不然会切到更长的号码中间）
_START = r"(?<![0-9A-Za-z])"
_END = r"(?![0-9A-Za-z])"

_MY_IC = re.compile(_START + r"(\d{6})([- ]?)(\d{2})([- ]?)(\d{4})" + _END)
# 新加坡 NRIC / FIN 也符合这个格式（1 个字母 + 7 位数字 + 1 个字母），遮法一样
_PASSPORT = re.compile(_START + r"([A-Za-z]{1,2}\d{6,8}[A-Za-z]?)" + _END)
_KEYWORD = re.compile(
    r"(?:(?<![A-Za-z])(?:nric|mykad|passport|i/c|ic|kp)(?![A-Za-z])|护照|身份证)"
    r"(?:\s*(?:no\.?|number|num|号码|号|是|为|:|：|#|-))*\s*"
    # 后面接着 * 的（例 900101-**-****，已经遮过）不再遮：遮两次结果一样
    r"([A-Za-z]{0,2} ?\d[\d\- ]{4,18}\d[A-Za-z]?)(?![0-9A-Za-z*]|[- ]+\*)",
    re.IGNORECASE,
)


def _mask_last(text: str, n: int = 6) -> str:
    """把最后 n 个英文字母 / 数字换成 *，- 和空格照留。"""
    chars = list(text)
    left = n
    for i in range(len(chars) - 1, -1, -1):
        if left == 0:
            break
        if chars[i].isalnum():
            chars[i] = MASK
            left -= 1
    return "".join(chars)


def _my_ic(m: re.Match) -> str:
    birth, sep1, mid, sep2, last = m.groups()
    return f"{birth}{sep1}{MASK * len(mid)}{sep2}{MASK * len(last)}"


def _keyword(m: re.Match) -> str:
    number = m.group(1)
    if sum(c.isalnum() for c in number) < 6:
        return m.group(0)
    start = m.start(1) - m.start(0)
    return m.group(0)[:start] + _mask_last(number)


def mask_id_numbers(text: str) -> str:
    """遮掉 text 里的 IC / 护照号码的后面 6 位。没有号码就原样回传。"""
    # 有关键字的先遮（遮过的有 *，下面两种格式就不会再对上，不会连生日也遮掉）
    text = _KEYWORD.sub(_keyword, text)
    text = _MY_IC.sub(_my_ic, text)
    return _PASSPORT.sub(lambda m: _mask_last(m.group(1)), text)
