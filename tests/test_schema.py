import pytest
from pydantic import ValidationError

from event_parser_llm.schema import EventInfo, event_json_schema

VALID = {
    "title": "ABC夏祭り2026",
    "category": "festival",
    "start_date": "2026-08-15",
    "end_date": "2026-08-16",
    "start_time": "17:00",
    "end_time": "21:00",
    "venue_name": "中央公園",
    "address": None,
    "price": "無料",
    "organizer": "ABC商店街",
    "summary": "屋台と盆踊りの夏祭り",
}


def test_valid_event_passes():
    event = EventInfo.model_validate(VALID)
    assert event.start_date == "2026-08-15"


def test_bad_date_format_is_rejected():
    with pytest.raises(ValidationError):
        EventInfo.model_validate({**VALID, "start_date": "2026/8/15"})


def test_unknown_category_is_rejected():
    with pytest.raises(ValidationError):
        EventInfo.model_validate({**VALID, "category": "sports"})


def test_schema_forbids_extra_keys():
    assert event_json_schema()["additionalProperties"] is False
