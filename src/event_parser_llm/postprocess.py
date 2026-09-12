"""LLM の生出力(dict)を正規化し、EventInfo として検証する。両バックエンド共通。"""

import re
from datetime import date, timedelta

from .schema import EventInfo

_WAREKI_BASE = {"令和": 2018, "平成": 1988, "昭和": 1925}

_DATE_PATTERNS = [
    re.compile(r"(?P<y>\d{4})[-/年.](?P<m>\d{1,2})[-/月.](?P<d>\d{1,2})"),
    re.compile(r"(?P<era>令和|平成|昭和)(?P<ey>\d{1,2}|元)年(?P<m>\d{1,2})月(?P<d>\d{1,2})日"),
    re.compile(r"(?P<m>\d{1,2})[/月](?P<d>\d{1,2})"),
]

_TIME_RE = re.compile(r"(?P<h>\d{1,2})[:時](?P<mi>\d{1,2})?")


def _infer_year(month: int, day: int, fetched_on: date) -> int:
    """年なし日付は取得日基準。2か月以上前なら翌年とみなす。"""
    try:
        candidate = date(fetched_on.year, month, day)
    except ValueError:
        return fetched_on.year
    if candidate < fetched_on - timedelta(days=60):
        return fetched_on.year + 1
    return fetched_on.year


def normalize_date(value: str | None, fetched_on: date) -> str | None:
    if not value:
        return None
    for pattern in _DATE_PATTERNS:
        m = pattern.search(value.strip())
        if not m:
            continue
        g = m.groupdict()
        if g.get("era"):
            era_year = 1 if g["ey"] == "元" else int(g["ey"])
            year = _WAREKI_BASE[g["era"]] + era_year
        elif g.get("y"):
            year = int(g["y"])
        else:
            year = _infer_year(int(g["m"]), int(g["d"]), fetched_on)
        try:
            return date(year, int(g["m"]), int(g["d"])).isoformat()
        except ValueError:
            return None
    return None


def normalize_time(value: str | None) -> str | None:
    if not value:
        return None
    m = _TIME_RE.search(value.strip())
    if not m:
        return None
    hour = int(m.group("h"))
    minute = int(m.group("mi") or 0)
    if hour > 29 or minute > 59:  # ライブハウスの「25:00」のような深夜表記は許す
        return None
    return f"{hour:02d}:{minute:02d}"


def _clean_str(value) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def finalize(raw: dict, fetched_on: date) -> EventInfo:
    data = dict(raw)
    data["start_date"] = normalize_date(data.get("start_date"), fetched_on)
    data["end_date"] = normalize_date(data.get("end_date"), fetched_on) or data["start_date"]
    data["start_time"] = normalize_time(data.get("start_time"))
    data["end_time"] = normalize_time(data.get("end_time"))
    for key in ("venue_name", "address", "price", "organizer"):
        data[key] = _clean_str(data.get(key))
    data["title"] = (_clean_str(data.get("title")) or "")
    data["summary"] = (data.get("summary") or "")[:100]
    return EventInfo.model_validate(data)
