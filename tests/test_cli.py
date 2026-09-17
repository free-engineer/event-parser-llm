import json

from event_parser_llm import pipeline
from event_parser_llm.cli import main

FAKE = {
    "title": "テストライブ", "category": "live",
    "start_date": "2026-10-01", "end_date": None,
    "start_time": "19:00", "end_time": None,
    "venue_name": "渋谷クラブ", "address": None,
    "price": "3,000円", "organizer": None, "summary": "テスト",
}


def test_parse_text_file(tmp_path, monkeypatch, capsys):
    # バックエンドを差し替えて、API や llama-server なしで CLI 全体を通す
    monkeypatch.setattr(pipeline, "get_backend", lambda name: (lambda text, fetched_on: FAKE))
    src = tmp_path / "page.txt"
    src.write_text("テストライブ 2026年10月1日 19:00 渋谷クラブ", encoding="utf-8")

    assert main(["parse", str(src), "--backend", "local"]) == 0

    out = json.loads(capsys.readouterr().out)
    assert out["event"]["title"] == "テストライブ"
    assert out["event"]["end_date"] == "2026-10-01"  # finalize が補完している
    assert out["backend"] == "local"
