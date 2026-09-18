"""Chinese numeral and indexed-entity normalization."""
from __future__ import annotations

import re


_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}
_CHINESE_NUMBER_RE = r"[零〇一二三四五六七八九十百千万两]+"


def chinese_number_to_int(value: str) -> int | None:
    text = (value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if any(char not in _DIGITS and char not in _UNITS for char in text):
        return None

    total = 0
    section = 0
    number = 0
    for char in text:
        if char in _DIGITS:
            number = _DIGITS[char]
            continue
        unit = _UNITS[char]
        if unit == 10000:
            section = (section + number) * unit
            total += section
            section = 0
            number = 0
        else:
            section += (number or 1) * unit
            number = 0
    return total + section + number


def normalize_indexed_entity(value: str) -> str | None:
    text = (value or "").strip()
    match = re.fullmatch(rf"企业\s*(\d+|{_CHINESE_NUMBER_RE})", text, re.I)
    if match:
        number = chinese_number_to_int(match.group(1))
        return f"企业{number}" if number is not None else None
    match = re.fullmatch(rf"ENT\s*(\d+|{_CHINESE_NUMBER_RE})", text, re.I)
    if match:
        number = chinese_number_to_int(match.group(1))
        return f"ENT{number}" if number is not None else None
    match = re.fullmatch(rf"company\s+(\d+|{_CHINESE_NUMBER_RE})", text, re.I)
    if match:
        number = chinese_number_to_int(match.group(1))
        return f"company {number}" if number is not None else None
    return None


def numeric_entity_key(value: str) -> str | None:
    normalized = normalize_indexed_entity(value)
    match = re.search(r"(\d+)", normalized or value or "")
    return match.group(1).lstrip("0") or "0" if match else None
