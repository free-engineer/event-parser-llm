# 作業日誌

> これは著者の実記録です。同じ手順を自分で試す人は `docs/journal.template.md` を使ってください。

## 2026-09-11
- 設計書と手順書を作成。方針: API 版 → データセット → 0.5B を LoRA 学習 → 2GB VPS。

## 2026-09-12
- CLI 実装
```
$ uv run event-parser parse "https://www.mlit.go.jp/report/press/kaiji05_hh_000347.html" --backend claude
{
  "event": {
    "title": "造船業界におけるAI・ロボティクス普及に向けたシンポジウム",
    "category": "other",
    "start_date": "2026-10-06",
    "end_date": "2026-10-06",
    "start_time": "13:30",
    "end_time": "17:30",
    "venue_name": "東京コンファレンスセンター・品川(大ホール)",
    "address": null,
    "price": "無料",
    "organizer": "国立研究開発法人海上・港湾・航空技術研究所 海上技術安全研究所、株式会社日本能率協会コンサルティング",
    "summary": "AI・ロボット技術の最新動向や他産業の活用事例を共有し、造船業の将来像を展望するシンポジウム。基調講演、事例発表、パネルディスカッションを実施。オンライン配信あり、要事前登録。"
  },
  "source_url": "https://www.mlit.go.jp/report/press/kaiji05_hh_000347.html",
  "fetched_on": "2026-09-12",
  "backend": "claude",
  "elapsed_sec": 8.76
}
```

## 2026-10-05
- HTTP API 実装
```
# terminal 1
$ EVENT_PARSER_BACKEND=claude uv run uvicorn event_parser_llm.api:app

# terminal 2
$ curl -s -X POST localhost:8000/parse -H 'Content-Type: application/json' -d '{"url": "https://www.mlit.go.jp/report/press/kaiji05_hh_000347.html"}'

{
  "event": {
    "title": "造船業界におけるAI・ロボティクス普及に向けたシンポジウム",
    "category": "other",
    "start_date": "2026-10-06",
    "end_date": "2026-10-06",
    "start_time": "13:30",
    "end_time": "17:30",
    "venue_name": "東京コンファレンスセンター・品川(大ホール)",
    "address": null,
    "price": "無料",
    "organizer": "国立研究開発法人海上・港湾・航空技術研究所 海上技術安全研究所、株式会社日本能率協会コンサルティング",
    "summary": "造船業の人手不足対策と生産性向上に向け、AI・ロボット技術の最新動向や他産業の事例を共有するシンポジウム。基調講演、事例発表、進捗報告、パネル討論を行い、オンライン配信もある。事前登録制。"
  },
  "source_url": "https://www.mlit.go.jp/report/press/kaiji05_hh_000347.html",
  "fetched_on": "2026-10-05",
  "backend": "claude",
  "elapsed_sec": 9.81
}
```