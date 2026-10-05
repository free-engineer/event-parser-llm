from fastapi.testclient import TestClient

from event_parser_llm import api, pipeline

FAKE = {
    "title": "テストライブ", "category": "live",
    "start_date": "2026-10-01", "end_date": None,
    "start_time": "19:00", "end_time": None,
    "venue_name": "渋谷クラブ", "address": None,
    "price": "3,000円", "organizer": None, "summary": "テスト",
}


def test_parse_text_endpoint(monkeypatch):
    monkeypatch.setattr(pipeline, "get_backend", lambda name: (lambda text, fetched_on: FAKE))
    client = TestClient(api.app)
    res = client.post("/parse", json={"text": "テストライブ 2026年10月1日"})
    assert res.status_code == 200
    assert res.json()["event"]["title"] == "テストライブ"


def test_parse_requires_exactly_one_of_url_or_text():
    client = TestClient(api.app)
    assert client.post("/parse", json={}).status_code == 422


def test_api_key_is_checked(monkeypatch):
    # 鍵が合った後の経路も差し替えておく(差し替えないと llama-server への接続待ちで固まる)
    monkeypatch.setattr(pipeline, "get_backend", lambda name: (lambda text, fetched_on: FAKE))
    monkeypatch.setattr(api, "API_KEY", "secret")
    client = TestClient(api.app)
    assert client.post("/parse", json={"text": "x"}).status_code == 401
    ok = client.post("/parse", json={"text": "x"}, headers={"X-API-Key": "secret"})
    assert ok.status_code == 200
