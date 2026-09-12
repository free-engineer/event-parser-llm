from datetime import date

from event_parser_llm.postprocess import finalize, normalize_date, normalize_time

TODAY = date(2026, 9, 2)


def test_normalize_date_variants():
    assert normalize_date("2026年8月15日", TODAY) == "2026-08-15"
    assert normalize_date("2026/8/15(土)", TODAY) == "2026-08-15"
    assert normalize_date("令和8年8月15日", TODAY) == "2026-08-15"
    assert normalize_date("2026-08-15", TODAY) == "2026-08-15"


def test_year_is_inferred_from_fetch_date():
    assert normalize_date("8/15", TODAY) == "2026-08-15"  # 2か月以内の過去 → 今年
    assert normalize_date("1/10", TODAY) == "2027-01-10"  # 大きく過去 → 翌年


def test_normalize_date_returns_none_when_unparseable():
    assert normalize_date("未定", TODAY) is None
    assert normalize_date(None, TODAY) is None


def test_normalize_time_variants():
    assert normalize_time("17:00") == "17:00"
    assert normalize_time("17時30分") == "17:30"
    assert normalize_time("9時") == "09:00"
    assert normalize_time("未定") is None


def test_finalize_fills_end_date_and_validates():
    raw = {
        "title": "テスト", "category": "live",
        "start_date": "2026年10月1日", "end_date": None,
        "start_time": "19時", "end_time": None,
        "venue_name": " 渋谷クラブ ", "address": "",
        "price": None, "organizer": None, "summary": "x" * 200,
    }
    event = finalize(raw, TODAY)
    assert event.end_date == "2026-10-01"
    assert event.start_time == "19:00"
    assert event.venue_name == "渋谷クラブ"
    assert event.address is None
    assert len(event.summary) == 100
