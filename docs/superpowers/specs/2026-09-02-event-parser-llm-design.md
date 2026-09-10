# event-parser-llm 設計書

作成日: 2026-09-02
状態: 承認済み(チャットでの設計レビューを反映)

## 1. 目的

日本語で書かれた Web 上のイベント情報(ライブ、祭り、飲食イベント、展覧会など)のページを入力に、日時・場所などを抜き出して JSON に変換するプログラムを作る。抽出の本体は、小型のオープンモデルを自分で微調整した「自作モデル」とし、メモリ 2GB の VPS 上で稼働させる。

副目的として、制作の経緯を Zenn の技術記事(連載)として公開する。

## 2. 前提と制約

| 項目 | 内容 |
|---|---|
| 作業者 | 本人がすべての作業を行う(学習目的)。この設計書と手順書はそのためのガイド |
| VPS | メモリ 2GB / 仮想 3 コア / NVMe 50GB。契約済み。学習には使えない(推論専用) |
| 学習環境 | Google Colab 無料枠(T4, VRAM 16GB)。ローカル PC(WSL2)に GPU はない |
| 応答時間 | 1 件あたり数十秒〜1 分まで許容 |
| 入力 | URL または本文テキスト。1 ページ = 1 イベントの詳細ページのみ対象 |
| 出力 | 検証済みの JSON |
| インターフェース | CLI と HTTP API の両方 |
| 言語・ツール | Python 3.12、uv、FastAPI、llama.cpp、HuggingFace TRL + PEFT |
| 教師データ | ハイブリッド: 最初の 30〜50 件は手作業、残りは Claude の下書きを人がレビュー |
| 教師モデルの呼び方 | Claude Code のヘッドレスモード(`claude -p`)。契約済みの Claude Max x5 プランの範囲で動かし、Anthropic API(従量課金)と API キーは使わない |
| ベースモデル | Qwen2.5-0.5B-Instruct から始め、精度が足りなければ 1.5B に上げる |
| 記事管理 | Zenn の Web エディタで執筆(GitHub 連携はしない) |

## 3. 対象外(YAGNI)

- 一覧ページ(1 ページに複数イベント)の抽出
- JavaScript 実行が必要なページの取得(Playwright 等は 2GB に載せない)
- 複数公演・複数日程を個別に構造化すること(開始日と終了日の範囲で表す)
- ユーザー管理、認証基盤、DB への保存
- GPU 推論、バッチ推論の最適化

## 4. 全体像とフェーズ

```
[URL / テキスト]
   │ fetch.py: HTML 取得 → 本文抽出 (trafilatura) → 正規化 (NFKC, 3000 文字上限)
   ▼
[本文テキスト + 取得日]
   │ prompt.py: 共通プロンプト
   ▼
[抽出バックエンド]  ── claude: Claude Code ヘッドレス (教師・ベースライン、Max プラン)
                    └─ local : llama-server (自作モデル, JSON Schema で文法制約)
   │ 生の dict
   ▼
[postprocess.py] 日付・時刻の正規化 → Pydantic で検証
   ▼
[ParseResult JSON]  ← cli.py / api.py が返す
```

| フェーズ | 内容 | 成果物 / タグ |
|---|---|---|
| 0 | 環境とリポジトリの準備 | GitHub リポジトリ、uv プロジェクト |
| 1 | Claude 版パイプライン | 動く CLI / HTTP API (backend=claude) / `v0.1.0` |
| 2 | データセット構築 | 300〜500 件の正解 JSON、train/dev/test 分割 / `v0.2.0` |
| 3 | ローカル推論基盤とベースライン測定 | llama.cpp、素の 0.5B と Claude の評価結果 / `v0.3.0` |
| 4 | LoRA 学習と量子化 | 学習済み GGUF、学習後の評価結果 / `v0.4.0` |
| 5 | VPS デプロイ | systemd で常駐する API / `v0.5.0` |
| 6 | 比較評価と記事化 | 3 者比較表、Zenn 連載 |

フェーズ 3 を学習より前に置く理由: 素の 0.5B の結果を先に測っておくと、学習の効果が数値で示せる。また llama.cpp の動作確認を学習前に済ませておける。

## 5. 出力スキーマ

LLM に出力させるのは `EventInfo` のみ。`source_url` などモデルが知り得ない情報はパイプライン側で付ける。

```json
{
  "title": "〇〇夏祭り2026",
  "category": "festival",
  "start_date": "2026-08-15",
  "end_date": "2026-08-16",
  "start_time": "17:00",
  "end_time": "21:00",
  "venue_name": "〇〇公園",
  "address": "東京都〇〇区〇〇1-2-3",
  "price": "無料",
  "organizer": "〇〇商店街振興組合",
  "summary": "100文字以内の要約"
}
```

- `category` は `live / festival / food / exhibition / other` の 5 値
- 日付は `YYYY-MM-DD`、時刻は `HH:MM`(24 時間表記)。本文に年がない場合は取得日を基準に推定し、取得日より 2 か月以上前になるなら翌年とみなす
- 1 日開催なら `end_date` は `start_date` と同じ
- 不明な項目は `null`。推測で埋めない
- 型はすべて文字列または null にし、小型モデルでも出力しやすくする。形式のチェックは Pydantic のバリデータで行う
- `extra="forbid"` にして `additionalProperties: false` を JSON Schema に出す(Claude Code の `--json-schema` と llama.cpp の文法制約の両方にそのまま渡す)

CLI / HTTP API が返す `ParseResult` は `EventInfo` を包む。

```json
{
  "event": { ...EventInfo... },
  "source_url": "https://…",
  "fetched_on": "2026-09-02",
  "backend": "local",
  "elapsed_sec": 21.3
}
```

## 6. コンポーネントとインターフェース

パッケージ名は `event_parser_llm`(uv の既定に合わせる)。

| モジュール | 責務 | 主な公開関数 |
|---|---|---|
| `fetch.py` | URL 取得、本文抽出、正規化 | `fetch_url(url) -> Page`, `page_from_text(text) -> Page`, `html_to_text(html) -> str`, `normalize_text(text) -> str` |
| `schema.py` | Pydantic モデルと JSON Schema | `EventInfo`, `ParseResult`, `event_json_schema() -> dict` |
| `prompt.py` | 共通プロンプト | `SYSTEM_PROMPT`, `build_user_message(text, fetched_on) -> str`, `build_messages(text, fetched_on) -> list[dict]` |
| `backends/claude.py` | `claude -p --json-schema` を subprocess で呼んで抽出 | `extract(text, fetched_on) -> dict` |
| `backends/local.py` | llama-server で抽出 | `extract(text, fetched_on) -> dict` |
| `backends/__init__.py` | 名前でバックエンドを選ぶ | `get_backend(name) -> Extractor` |
| `postprocess.py` | 正規化と検証 | `normalize_date`, `normalize_time`, `finalize(raw, fetched_on) -> EventInfo` |
| `pipeline.py` | 上記をつなぐ | `parse_url(url, backend) -> ParseResult`, `parse_text(text, backend) -> ParseResult` |
| `metrics.py` | 評価指標 | `compare(pred, gold) -> dict[str, bool]`, `summarize(results) -> dict[str, float]` |
| `cli.py` | `event-parser parse <URL or ファイル> --backend claude/local` | `main(argv)` |
| `api.py` | FastAPI: `POST /parse`, `GET /health` | `app` |

バックエンドは「本文と取得日を受け取り、生の dict を返す」関数に統一する。正規化と検証は両バックエンドで同じ `finalize()` を通す。これにより、教師(Claude)と生徒(自作モデル)の入出力の条件が揃う。

### Claude バックエンドの仕組み

`claude -p --output-format json --json-schema <EventInfo の JSON Schema> --system-prompt <SYSTEM_PROMPT> --model opus --effort medium --tools "" --max-turns 1 --no-session-persistence` を subprocess で起動し、ユーザーメッセージを標準入力で渡す。結果は 1 行の JSON で、`structured_output` にスキーマ検証済みの dict、`total_cost_usd` に API 換算額、`is_error` に失敗フラグが入る(2026-09-02 に Claude Code 2.1.258 で動作確認済み)。`--tools ""` でツールを外すと前置きが約 2.2 万トークンから約 7 千トークンに減る。認証は Claude Code の通常のログイン(Max プラン)をそのまま使う。`--bare` は OAuth 認証を無効にするので付けない。OAuth トークンを取り出して SDK や curl から API を直接叩くのは利用規約上できないので、必ず `claude` コマンド経由にする。

### 本文テキストの規約

学習時と推論時で入力の作り方が変わると精度が落ちるため、次を固定する。

- trafilatura で本文抽出(コメント除外、表は含める、recall 優先)。抽出できない場合は lxml でタグを剥がした粗いテキストにフォールバック
- NFKC 正規化(全角英数字を半角に)、行頭行末の空白除去、空行除去
- 先頭 3000 文字で打ち切り(Qwen のトークナイザで概ね 2000〜2500 トークン)
- ユーザーメッセージは `取得日: YYYY-MM-DD\n\n本文:\n<本文>` の形

## 7. モデルと推論基盤

| 項目 | 決定 |
|---|---|
| ベースモデル | `Qwen/Qwen2.5-0.5B-Instruct`(Apache-2.0)。次候補は `Qwen/Qwen2.5-1.5B-Instruct` |
| 量子化 | 0.5B は Q8_0(約 0.53GB)。小さいモデルは 4bit で劣化が目立つため 8bit にする。1.5B に上げる場合は Q4_K_M(約 1.1GB) |
| 推論サーバ | llama.cpp の `llama-server`。VPS 上でソースからビルド(そのCPU向けに最適化される) |
| 起動オプション | `-c 4096 -t 3 -np 1 --host 127.0.0.1 --port 8080` |
| 出力制約 | `/v1/chat/completions` の `response_format: {"type": "json_schema", "schema": <EventInfo の JSON Schema>}`。文法制約で JSON の妥当性を保証 |
| 温度 | 0(決定的) |

メモリ見積り(0.5B Q8_0): モデル 0.53GB + KV キャッシュ(4096 トークン) 約 0.05GB + 作業領域 約 0.15GB + FastAPI 約 0.1GB + OS 約 0.3GB = 約 1.1GB。2GB に十分収まる。1.5B Q4_K_M に上げた場合は約 1.8GB で余裕が薄くなるため、NVMe 上に 2GB のスワップを作っておく。

速度見積り(3 vCPU, 0.5B Q8_0): 入力 2000 トークンの処理に約 10 秒、出力 300 トークンに約 10〜15 秒。1 件 20〜30 秒程度。これは推定値なので、フェーズ 5 で実測して記録する。

## 8. 学習

| 項目 | 決定 |
|---|---|
| 環境 | Google Colab 無料枠(T4) |
| 手法 | LoRA(PEFT)。T4 は bf16 非対応なので fp32 で学習(0.5B なら余裕で載る) |
| フレームワーク | TRL `SFTTrainer` + `SFTConfig`。データは conversational prompt-completion 形式。既定で completion(assistant 側)だけに損失をかける |
| LoRA 設定 | r=16, alpha=32, dropout=0.05, 対象は q/k/v/o/gate/up/down の全射影 |
| 学習設定 | 3 エポック、学習率 1e-4、cosine、batch 2 × 勾配蓄積 4、max_length 3072、gradient checkpointing 有効 |
| 成果物 | LoRA アダプタ(Drive に保存) → ベースに合成 → fp16 で保存 → `convert_hf_to_gguf.py --outtype q8_0` で GGUF |

注意点: `SFTConfig` は `fp16` 未指定だと `bf16=True` が既定になるので、T4 では `bf16=False` を明示する。

## 9. データセット

| 項目 | 決定 |
|---|---|
| 規模 | 300〜500 ページ。test 50 件は最初に確保し、学習には一切使わない |
| 収集元 | 自治体・観光協会のイベント欄、ライブハウスのスケジュール、美術館・ギャラリーの展覧会、商業施設の催事、飲食店のイベント告知など。ジャンルとサイト構造をばらけさせる |
| 収集マナー | robots.txt を確認、3 秒間隔、User-Agent を明示 |
| ラベル作成 | 最初の 30〜50 件は手作業。残りは Claude(Claude Code 経由、`--model opus --effort medium`)で下書き → 本文と突き合わせて修正 → 採用 |
| 分割 | カテゴリで層化して 80/10/10(train/dev/test)。乱数シード固定 |
| 保存形式 | TRL の conversational prompt-completion(`prompt` に system+user、`completion` に assistant の JSON 文字列)。評価用に `id`, `text`, `fetched_on`, `gold` も同じ行に持つ |
| 公開範囲 | GitHub に置くのは URL 一覧、manifest、正解 JSON のみ。本文テキストは著作物なので `.gitignore` して手元だけに置く |

費用: Claude Code は Max x5 プランの範囲で動くので追加請求はない。ただし 5 時間ごとの使用量上限があるため、下書きは 50 件ずつに分けて実行する。1 回の呼び出しは前置き約 7 千トークン(ツール無効化時) + 本文 2〜3 千トークン + 出力(思考含む)数百トークン。結果 JSON の `total_cost_usd` は API 換算額で実際には請求されないが、記事用に記録する(1 件あたり約 $0.08、500 件で約 $40 相当)。

## 10. 評価

| 指標 | 定義 |
|---|---|
| 項目別正解率 | title, category, start_date, end_date, start_time, end_time, venue_name は正規化後の完全一致。address, price, organizer は片方がもう片方を含めば正解 |
| コア全項目正解率 | title, category, start_date, end_date, start_time, venue_name がすべて正解の割合 |
| JSON 妥当率 | 出力が `EventInfo` として検証を通った割合 |
| 応答時間 | 1 件あたりの中央値と最大値 |

比較対象は 3 つ: 素の Qwen2.5-0.5B-Instruct(学習前)、LoRA 学習後、Claude API。同じ test 50 件、同じ `scripts/evaluate.py` で測る。

## 11. デプロイ

- Ubuntu 上に `app` ユーザーを作り、`/home/app/event-parser-llm` にリポジトリを clone。`uv sync --no-dev` で依存を入れる
- llama.cpp は `/home/app/llama.cpp` にソースからビルド(`llama-server` のみ)
- GGUF は `scp` で `/home/app/event-parser-llm/models/` に置く
- systemd ユニット 2 つ: `llama-server.service`(先に起動)と `event-parser-api.service`(uvicorn, worker 1)
- HTTP API は `X-API-Key` ヘッダで簡易認証。鍵は `.env` に置き、`EnvironmentFile` で読む
- ufw で 22 と 8000 のみ開ける。llama-server は 127.0.0.1 のみで待ち受け
- 更新は `git pull && uv sync --no-dev && systemctl restart event-parser-api`

## 12. エラー処理

| 状況 | 振る舞い |
|---|---|
| URL 取得失敗(4xx/5xx, タイムアウト) | 例外。API は 422 でメッセージを返す |
| 本文抽出が空 | lxml フォールバック。それでも空なら例外 |
| LLM 出力が JSON として壊れている | local は文法制約で起きない前提。Claude Code は `--json-schema` で検証済みの `structured_output` を返す。それでも起きたら例外 |
| 日付・時刻の形式違反 | `postprocess` で正規化し、直せなければ `null` |
| `claude -p` が失敗(終了コード非 0、`is_error`、使用量上限) | 例外にして記録。下書きスクリプトは 3 連続失敗で停止し、次の 5 時間ウィンドウで再開する |
| llama-server 未起動 | 接続エラーを例外に。API は 422 |

## 13. テスト方針

- 純粋関数(正規化、日付推定、指標)は pytest で単体テスト
- fetch は HTML 文字列を使ったテスト(ネットワークに出ない)
- CLI と API はバックエンドを差し替えて(monkeypatch)テスト
- Claude / llama-server を実際に呼ぶ確認は手動のスモークテスト(手順書に手順を書く)

## 14. GitHub と Zenn の運用

- リポジトリ `event-parser-llm` を公開で作る。Colab から `pip install git+https://github.com/<user>/event-parser-llm` して、プロンプトや評価コードを学習側と共有する
- フェーズ完了ごとに `v0.1.0` 〜 `v0.5.0` のタグを打ち、記事から「この時点のコード」として参照する
- 記事は Zenn の Web エディタで書く。素材(コマンド出力、数値、スクショ、つまずき)は `docs/journal.md` に日付付きで残す
- 連載構成(案): (1) 構想と設計 (2) Claude 版を作る(Max プランの Claude Code をヘッドレス利用) (3) データセット作りの実際 (4) 0.5B を llama.cpp で動かしてベースラインを測る (5) Colab で LoRA 学習 (6) 2GB VPS にデプロイ (7) 3 者比較とまとめ

## 15. リスクと退路

| リスク | 兆候 | 退路 |
|---|---|---|
| 0.5B の精度が足りない | 学習後もコア全項目正解率が Claude の半分以下 | データを増やす → 1.5B に上げる(Q4_K_M、約 1.8GB。スワップ前提) |
| VPS で遅い | 1 件 60 秒超 | 入力上限を 2000 文字に下げる、`-c 3072` に縮める |
| メモリ不足 | OOM で llama-server が落ちる | スワップ、`-c` を縮める、Q4_K_M に落とす |
| Colab のセッション切れ | 学習途中で止まる | `save_strategy="epoch"` で Drive に保存し、`resume_from_checkpoint` で再開 |
| trafilatura が本文を取れないサイト | 空や断片的なテキスト | lxml フォールバック。それでも駄目なサイトはデータから外す |
| ラベル付けの負荷 | 進まない | 手作業は 30 件で止め、残りは下書きレビューに切り替える |
