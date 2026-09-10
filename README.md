# event-parser-llm

日本語のイベントページ(URL またはテキスト)から、日時・場所などを抽出して JSON にする。
抽出は自作の小型モデル(Qwen2.5-0.5B-Instruct を LoRA 学習)で行い、メモリ 2GB の VPS で動かす。

- 設計書: docs/superpowers/specs/2026-09-02-event-parser-llm-design.md
- 手順書: docs/superpowers/plans/2026-09-02-event-parser-llm-plan.md

## 作業日誌

手順書のとおりに進めながら、コマンド出力・数値・つまずきを日誌に残している。

- `docs/journal.md` — 著者の実記録
- `docs/journal.template.md` — ひな形

同じ手順を自分で試す場合は、ひな形を上書きコピーして使う。

```bash
cp docs/journal.template.md docs/journal.md
```
