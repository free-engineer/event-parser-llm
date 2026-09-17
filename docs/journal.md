# 作業日誌

> これは著者の実記録です。同じ手順を自分で試す人は `docs/journal.template.md` を使ってください。

## 2026-09-11
- 設計書と手順書を作成。方針: API 版 → データセット → 0.5B を LoRA 学習 → 2GB VPS。

## 2026-09-12
- CLI 実装
```
$ uv run event-parser parse "https://www.my.metro.tokyo.lg.jp/w/000-20260908-266726618" --backend claude
{
  "event": {
    "title": "秋の東京産を知る旬のスイーツレッスン",
    "category": "food",
    "start_date": "2026-10-01",
    "end_date": "2026-10-01",
    "start_time": "13:00",
    "end_time": "15:00",
    "venue_name": "かわせみ亭",
    "address": "東京都文京区本駒込",
    "price": "無料",
    "organizer": "TOKYO GROWN",
    "summary": "東京産農林水産物の魅力を体験する地産地消型料理教室。稲城の新高梨のカップスイーツと東京産秋の旬サラダプレートを作り、生産者や「イイシナ」認証制度も紹介。定員5名。"
  },
  "source_url": "https://www.my.metro.tokyo.lg.jp/w/000-20260908-266726618",
  "fetched_on": "2026-09-12",
  "backend": "claude",
  "elapsed_sec": 18.23
}
```
