"""Lenient answer parsing shared by all conditions. Grading is about content, not formatting."""
import json
import re


def parse_json(text):
    """First JSON object in the text, with or without a ``` fence. None if there is none."""
    if not text:
        return None
    text = re.sub(r"```(?:json)?", "", text)
    dec = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            value, _ = dec.raw_decode(text, start)
            if isinstance(value, dict):
                return value
        except ValueError:
            pass
        start = text.find("{", start + 1)
    return None


def num(x):
    """1,700,000 / '1700000원' / 1700000.0 -> 1700000 (int when whole). None if not a number."""
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return int(x) if float(x).is_integer() else x
    s = re.sub(r"[,\s원개건%]", "", str(x or ""))
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if f.is_integer() else f


def same_set(a, b):
    """Order-insensitive comparison of two lists of strings."""
    if not isinstance(a, list) or not isinstance(b, list):
        return False
    return sorted(str(x).strip() for x in a) == sorted(str(x).strip() for x in b)
