"""Small helpers the harness copies into the model's working folder as helpers.py (standard library only).

    from helpers import num, norm
    num("2억6천만원") -> 260000000      num("(1,234)") -> -1234     num("$5.2") -> 5.2     num("12.5%") -> 12.5
    norm(" 스테이플러 심 ") == norm("스테이플러심")      norm("(주)한빛") == norm("한빛")
"""
import re

_SMALL = {"천": 1000, "백": 100, "십": 10}
_BIG = {"조": 10 ** 12, "억": 10 ** 8, "만": 10 ** 4}
_DIGITS = {"영": 0, "일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}


def _korean(s):
    """'2억6천만' -> 260000000. Digits and Korean digit words before 조/억/만/천/백/십."""
    total, section, cur = 0, 0, None
    i = 0
    while i < len(s):
        m = re.match(r"\d+(?:\.\d+)?", s[i:])
        if m:
            cur = float(m.group())
            i += len(m.group())
            continue
        ch = s[i]
        if ch in _DIGITS:
            cur = _DIGITS[ch]
        elif ch in _SMALL:
            section += (1 if cur is None else cur) * _SMALL[ch]
            cur = None
        elif ch in _BIG:
            section += 0 if cur is None else cur
            total += (section or 1) * _BIG[ch]
            section, cur = 0, None
        else:
            raise ValueError(f"not a number: {s!r}")
        i += 1
    total += section + (0 if cur is None else cur)
    return total


def num(text):
    """A number written the way people write it in reports and messages. Raises ValueError if there is none."""
    if isinstance(text, (int, float)):
        return text
    s = re.sub(r"^\s*([₩$€£¥]|USD|KRW|EUR)\s*", "", str(text).strip())
    neg = False
    if s.startswith("(") and s.endswith(")"):          # accounting negative: (1,234), $ (89.7)
        neg, s = True, s[1:-1].strip()
    s = s.replace("−", "-").replace("–", "-")
    s = re.sub(r"[\s,]", "", s)
    s = re.sub(r"^[₩$€£¥]|^(USD|KRW|EUR)", "", s)
    s = re.sub(r"(원|개|건|명|주|일|시간|%|퍼센트|USD|KRW)$", "", s)
    if s.startswith("-"):
        neg, s = not neg, s[1:]
    s = re.sub(r"^[₩$€£¥]", "", s)
    if not s:
        raise ValueError(f"not a number: {text!r}")
    if re.fullmatch(r"\d+(\.\d+)?", s):
        v = float(s)
    else:
        v = _korean(s)
    v = -v if neg else v
    return int(v) if float(v).is_integer() else v


def norm(text):
    """A key for comparing names: no spaces, case-folded, company-type marks removed."""
    s = str(text)
    s = re.sub(r"\(주\)|㈜|주식회사|\(유\)|㈲", "", s)
    return re.sub(r"\s+", "", s).casefold()
