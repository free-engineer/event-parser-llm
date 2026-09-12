# event-parser-llm 手順書(実装計画)

> **この文書の使い方:** 作業はすべて本人が行う。上から順にチェックボックスを埋めていく。各タスクは「テストを書く → 落ちるのを見る → 実装する → 通るのを見る → コミット」の順で進める。詰まったら `docs/journal.md` に日付と状況を書いてから調べる(記事のネタになる)。

**ゴール:** 日本語イベントページの URL かテキストを渡すと、自作の小型モデルが構造化 JSON を返す CLI / HTTP API を作り、2GB VPS で常駐させる。

**アーキテクチャ:** 取得 → 本文抽出 → 共通プロンプト → 抽出バックエンド(Claude Code ヘッドレス または llama-server) → 正規化・検証 → JSON。教師(Claude)で作ったデータで Qwen2.5-0.5B-Instruct を LoRA 学習し、GGUF に量子化して llama.cpp で動かす。

**技術スタック:** Python 3.12 / uv / pydantic / httpx / trafilatura / FastAPI / Claude Code CLI(ヘッドレス、Max プラン) / llama.cpp / TRL + PEFT(Colab)

**設計書:** `docs/superpowers/specs/2026-09-02-event-parser-llm-design.md`(この手順書は設計書の決定に基づく。迷ったら設計書に戻る)

## 全体の制約

- Python `>=3.12`、パッケージ名 `event_parser_llm`、CLI コマンド名 `event-parser`
- 本文テキストは NFKC 正規化 + 空行除去 + 先頭 3000 文字。学習時と推論時で必ず同じ関数を通す
- ユーザーメッセージの形は `取得日: YYYY-MM-DD\n\n本文:\n<本文>` に固定
- 教師モデルは Claude Code ヘッドレス(`claude -p --model opus --effort medium --tools ""`)。Anthropic API と API キーは使わない。`--bare` は OAuth を無効にするので付けない
- ベースモデルは `Qwen/Qwen2.5-0.5B-Instruct`、量子化は Q8_0
- llama-server は `127.0.0.1:8080`、`-c 4096`、温度 0
- 本文テキスト(`data/raw/`, `data/drafts/`, `data/dataset/`)、モデル(`models/`)、`.env` は Git に入れない
- フェーズ完了ごとにタグ `v0.1.0` 〜 `v0.5.0`

## 所要時間の目安

| フェーズ | 目安 | 備考 |
|---|---|---|
| 0 準備 | 1〜2 時間 | |
| 1 Claude 版 | 4〜6 時間 | |
| 2 データセット | 15〜25 時間 | 最も重い。数日に分ける |
| 3 ローカル推論基盤 | 4〜6 時間 | ビルド待ちを含む |
| 4 学習と量子化 | 4〜8 時間 | Colab の待ち時間を含む |
| 5 VPS デプロイ | 3〜5 時間 | |
| 6 記事化 | 記事 1 本あたり 3〜5 時間 | |

## 記事のために記録するもの

各フェーズで次を `docs/journal.md` に残す。後で記事に起こすときの一次資料になる。

- 実行したコマンドと、その出力の要点(エラー全文はそのまま貼る)
- 数値: 文字数、件数、費用(結果 JSON の `total_cost_usd`。API 換算額で実際は請求されない)、学習 loss、正解率、応答時間、`free -m` の結果
- スクリーンショット: Colab の学習ログ、`htop`、API のレスポンス
- 「想定と違ったこと」「やり直したこと」(記事で一番読まれる部分)
- 設計書のどの決定が正しく、どれを変えたか

---

## フェーズ 0: 準備

### タスク 0.1: GitHub リポジトリと uv プロジェクトの初期化

**作るもの:**
- `pyproject.toml`, `.gitignore`, `README.md`, `docs/journal.md`, `docs/journal.template.md`
- `src/event_parser_llm/__init__.py`(空)

- [ ] **ステップ 0: WSL に Linux 版の uv を入れる**

今の WSL で `which uv` を打つと Windows 側の pyenv のシム(`/mnt/c/Users/.../pyenv-win/shims/uv`)が見えるが、これは WSL からは実行できない。Linux 版を入れて、そちらが先に見つかるようにする。

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
which uv        # /home/shun/.local/bin/uv になっていること
uv --version
```

`which uv` がまだ `/mnt/c/...` を指す場合は、`~/.bashrc` の末尾に `export PATH="$HOME/.local/bin:$PATH"` を追加してシェルを開き直す。

- [ ] **ステップ 1: GitHub CLI のログイン状態を確認**

```bash
gh auth status
```

未ログインなら `gh auth login` を実行する(ブラウザ認証)。

- [ ] **ステップ 2: uv プロジェクトを作る**

```bash
cd ~/dev/event-parser-llm
git init -b main
uv init --package --name event-parser-llm
uv add httpx trafilatura lxml pydantic fastapi uvicorn
uv add --dev pytest
```

`uv init --package` が `src/event_parser_llm/__init__.py` と `pyproject.toml` を作る。`uv add` が `pyproject.toml` に依存を書き込み、`uv.lock` と `.venv` を作る。

- [ ] **ステップ 3: pyproject.toml を整える**

`[project.scripts]` を次の内容に置き換える(uv が生成した `event-parser-llm = "event_parser_llm:main"` は消す)。

```toml
[project.scripts]
event-parser = "event_parser_llm.cli:main"
```

`src/event_parser_llm/__init__.py` の中身は空にする(uv が生成した `main()` を消す)。

- [ ] **ステップ 4: .gitignore に追記**

```gitignore
# 本文テキスト・生成物・秘密情報は Git に入れない
.env
data/raw/
data/drafts/
data/dataset/
models/
*.gguf

# Python キャッシュ・バイトコード                                                                                                                    
__pycache__/                                                                                                                                         
*.py[cod]
*$py.class

# 仮想環境
.venv/

# pytest キャッシュ
.pytest_cache/
```

- [ ] **ステップ 5: README と journal を作る**

`README.md`:

```markdown
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
```

```bash
cp docs/journal.template.md docs/journal.md
```

`docs/journal.md`:

```markdown
# 作業日誌

## 2026-09-11
- 設計書と手順書を作成。方針: API 版 → データセット → 0.5B を LoRA 学習 → 2GB VPS。
```

- [ ] **ステップ 6: 最初のコミットと GitHub への push**

```bash
git add -A
git commit -m "chore: プロジェクト初期化と設計書"
gh repo create event-parser-llm --public --source=. --remote=origin --push
```

ブラウザでリポジトリが見えることを確認する。

### タスク 0.2: Claude Code(Max プラン)のヘッドレス呼び出しを確認

教師モデルは Anthropic API(従量課金)ではなく、契約済みの Claude Max x5 プランで動く Claude Code をヘッドレスモード(`claude -p`)で呼ぶ。API キーは不要。

- [ ] **ステップ 1: ログイン状態を確認**

```bash
claude auth status
```

期待: `"loggedIn": true`、`"authMethod": "claude.ai"`、`"subscriptionType": "max"`。違う場合は `claude auth login` でログインし直す。

- [ ] **ステップ 2: 構造化出力つきで 1 回呼んでみる**

```bash
printf '取得日: 2026-09-02\n\n本文:\nABC夏祭り 8月15日(土) 17:00〜21:00 中央公園 入場無料' \
  | claude -p --output-format json --tools "" --no-session-persistence --model opus --effort medium \
      --json-schema '{"type":"object","properties":{"title":{"type":"string"},"start_date":{"type":"string"},"price":{"anyOf":[{"type":"string"},{"type":"null"}]}},"required":["title","start_date","price"],"additionalProperties":false}' \
      --system-prompt "本文からイベント名、開始日(YYYY-MM-DD)、料金を JSON で返す。不明は null。"
```

期待: 1 行の JSON が返り、その中に `"structured_output":{"title":"ABC夏祭り","start_date":"2026-08-15","price":"無料"}` のような値が含まれる(price は「入場無料」でも良い)。`total_cost_usd` は API 換算額で、Max プランでは請求されない。`usage.cache_creation_input_tokens` が 7 千前後なら `--tools ""` が効いている(ツール有効だと約 2.2 万)。

注意 2 点。`--bare` を付けると OAuth(サブスク)認証が無効になり API キーを要求されるので付けない。OAuth トークンを取り出して SDK や curl から API を直接叩くのは利用規約違反になるので、必ず `claude` コマンド経由で使う。

- [ ] **ステップ 3: 使用量の見方を確認**

`claude` を対話モードで起動して `/usage` と打つと、5 時間ウィンドウと週の残量が見える(見えない場合は claude.ai の設定画面の使用量を見る)。フェーズ 2 の下書き作成は 50 件ずつ実行し、上限に当たったら次のウィンドウまで待つ。

---

## フェーズ 1: Claude 版パイプライン

### タスク 1.1: スキーマ

**ファイル:**
- 作成: `src/event_parser_llm/schema.py`
- テスト: `tests/test_schema.py`

**提供するもの:** `EventInfo`(Pydantic)、`ParseResult`、`event_json_schema() -> dict`

- [ ] **ステップ 1: 落ちるテストを書く**

`tests/test_schema.py`:

```python
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
```

- [ ] **ステップ 2: 落ちることを確認**

```bash
uv run pytest tests/test_schema.py -v
```

期待: `ModuleNotFoundError: No module named 'event_parser_llm.schema'` で失敗。

- [ ] **ステップ 3: 実装**

`src/event_parser_llm/schema.py`:

```python
"""抽出結果のスキーマ。教師(Claude)・生徒(ローカルモデル)・API 応答で共通に使う。"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal["live", "festival", "food", "exhibition", "other"]

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")


class EventInfo(BaseModel):
    """LLM に出力させる本体。source_url など LLM が知り得ない情報は含めない。"""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="イベント名。副題は含めない")
    category: Category = Field(
        description="live=音楽ライブ・コンサート, festival=祭り・地域行事, "
        "food=飲食関連イベント, exhibition=展覧会・展示, other=その他"
    )
    start_date: str | None = Field(description="開始日 YYYY-MM-DD。不明なら null")
    end_date: str | None = Field(
        description="終了日 YYYY-MM-DD。1日開催なら start_date と同じ値。不明なら null"
    )
    start_time: str | None = Field(description="開始時刻 HH:MM (24時間表記)。不明なら null")
    end_time: str | None = Field(description="終了時刻 HH:MM (24時間表記)。不明なら null")
    venue_name: str | None = Field(description="会場名。不明なら null")
    address: str | None = Field(description="会場の住所。不明なら null")
    price: str | None = Field(
        description="料金を短く。例: '前売3,000円 / 当日3,500円', '無料'。不明なら null"
    )
    organizer: str | None = Field(description="主催者。不明なら null")
    summary: str = Field(description="イベント内容の要約。100文字以内")

    @field_validator("start_date", "end_date")
    @classmethod
    def _check_date(cls, v: str | None) -> str | None:
        if v is not None and not DATE_RE.match(v):
            raise ValueError(f"日付は YYYY-MM-DD 形式にしてください: {v!r}")
        return v

    @field_validator("start_time", "end_time")
    @classmethod
    def _check_time(cls, v: str | None) -> str | None:
        if v is not None and not TIME_RE.match(v):
            raise ValueError(f"時刻は HH:MM 形式にしてください: {v!r}")
        return v


class ParseResult(BaseModel):
    """CLI / HTTP API が返す最終形。"""

    event: EventInfo
    source_url: str | None
    fetched_on: str
    backend: str
    elapsed_sec: float


def event_json_schema() -> dict:
    """llama.cpp の文法制約と Claude の structured outputs に渡す JSON Schema。"""
    return EventInfo.model_json_schema()
```

- [ ] **ステップ 4: 通ることを確認**

```bash
uv run pytest tests/test_schema.py -v
```

期待: 4 件 PASS。

- [ ] **ステップ 5: JSON Schema を眺めておく(記事ネタ)**

```bash
uv run python -c "import json; from event_parser_llm.schema import event_json_schema; print(json.dumps(event_json_schema(), ensure_ascii=False, indent=2))"
```

`str | None` が `anyOf` になっていること、`category` が `enum` になっていることを確認する。これがそのまま llama.cpp の文法になる。

- [ ] **ステップ 6: コミット**

```bash
git add src/event_parser_llm/schema.py tests/test_schema.py
git commit -m "feat: 抽出結果のスキーマを定義"
```

### タスク 1.2: 取得と本文抽出

**ファイル:**
- 作成: `src/event_parser_llm/fetch.py`
- テスト: `tests/test_fetch.py`

**提供するもの:** `Page`(dataclass: url, text, fetched_on)、`fetch_url(url) -> Page`、`page_from_text(text, fetched_on=None) -> Page`、`html_to_text(html) -> str`、`normalize_text(text) -> str`、定数 `MAX_CHARS = 3000`、`USER_AGENT`

- [ ] **ステップ 1: 落ちるテストを書く**

`tests/test_fetch.py`:

```python
from event_parser_llm.fetch import MAX_CHARS, html_to_text, normalize_text

HTML = """<html><head><title>テスト</title><style>body{}</style></head><body>
<nav>ホーム | お知らせ | アクセス</nav>
<article>
<h1>ＡＢＣ夏祭り２０２６</h1>
<p>日時：2026年8月15日（土）17:00〜21:00</p>
<p>会場：中央公園（東京都千代田区1-1）</p>
<p>入場無料。屋台や盆踊りをお楽しみください。雨天の場合は翌日に順延します。</p>
<p>主催：ABC商店街振興組合　お問い合わせ：03-0000-0000</p>
</article>
<script>console.log("x")</script>
<footer>© 2026 ABC商店街</footer></body></html>"""


def test_normalize_text_converts_fullwidth_and_drops_blank_lines():
    assert normalize_text("ＡＢＣ　１２３\n\n\n次の行  ") == "ABC 123\n次の行"


def test_normalize_text_truncates():
    assert len(normalize_text("あ" * (MAX_CHARS + 100))) == MAX_CHARS


def test_html_to_text_extracts_body_and_drops_script():
    text = html_to_text(HTML)
    assert "ABC夏祭り2026" in text
    assert "2026年8月15日" in text
    assert "console.log" not in text
```

- [ ] **ステップ 2: 落ちることを確認**

```bash
uv run pytest tests/test_fetch.py -v
```

期待: ImportError で失敗。

- [ ] **ステップ 3: 実装**

`src/event_parser_llm/fetch.py`:

```python
"""URL または HTML から、LLM に渡す本文テキストを作る。"""

import unicodedata
from dataclasses import dataclass
from datetime import date

import httpx
import lxml.html
import trafilatura

MAX_CHARS = 3000
USER_AGENT = "event-parser-llm/0.1 (personal study project)"


@dataclass
class Page:
    url: str | None
    text: str
    fetched_on: date


def normalize_text(text: str) -> str:
    """全角英数字を半角に揃え、空行を落とし、長さを揃える。学習時と推論時で必ずこれを通す。"""
    text = unicodedata.normalize("NFKC", text)
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    return text[:MAX_CHARS]


def _crude_text(html: str | bytes) -> str:
    """trafilatura が本文を見つけられなかったときの粗い代替。"""
    root = lxml.html.fromstring(html)
    for node in root.xpath("//script|//style|//nav|//header|//footer"):
        node.drop_tree()
    return root.text_content()


def html_to_text(html: str | bytes) -> str:
    extracted = trafilatura.extract(
        html, include_comments=False, include_tables=True, favor_recall=True
    )
    if not extracted:
        extracted = _crude_text(html)
    text = normalize_text(extracted)
    if not text:
        raise ValueError("本文を抽出できませんでした")
    return text


def fetch_url(url: str, timeout: float = 20.0) -> Page:
    response = httpx.get(
        url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=timeout
    )
    response.raise_for_status()
    # bytes のまま渡すと trafilatura / lxml が meta の charset を見て文字コードを判定する
    return Page(url=url, text=html_to_text(response.content), fetched_on=date.today())


def page_from_text(text: str, fetched_on: date | None = None) -> Page:
    return Page(url=None, text=normalize_text(text), fetched_on=fetched_on or date.today())
```

- [ ] **ステップ 4: 通ることを確認**

```bash
uv run pytest tests/test_fetch.py -v
```

期待: 3 件 PASS。

- [ ] **ステップ 5: 実ページで試す**

イベント詳細ページの URL を 1 つ選んで(自治体のイベント欄などで良い)、本文がどう抽出されるか見る。

```bash
uv run python -c "from event_parser_llm.fetch import fetch_url; p = fetch_url('ここにURL'); print(len(p.text)); print(p.text[:800])"
```

ナビゲーションやフッターが混ざっていないか、日付や会場が残っているかを確認し、結果を journal に書く。

- [ ] **ステップ 6: コミット**

```bash
git add src/event_parser_llm/fetch.py tests/test_fetch.py
git commit -m "feat: URL 取得と本文抽出"
```

### タスク 1.3: プロンプトと後処理

**ファイル:**
- 作成: `src/event_parser_llm/prompt.py`, `src/event_parser_llm/postprocess.py`
- テスト: `tests/test_postprocess.py`

**提供するもの:** `SYSTEM_PROMPT`、`build_user_message(text, fetched_on) -> str`、`build_messages(text, fetched_on) -> list[dict]`、`normalize_date(value, fetched_on) -> str | None`、`normalize_time(value) -> str | None`、`finalize(raw: dict, fetched_on) -> EventInfo`

- [ ] **ステップ 1: 落ちるテストを書く**

`tests/test_postprocess.py`:

```python
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
```

- [ ] **ステップ 2: 落ちることを確認**

```bash
uv run pytest tests/test_postprocess.py -v
```

- [ ] **ステップ 3: プロンプトを実装**

`src/event_parser_llm/prompt.py`:

```python
"""教師(Claude)と生徒(ローカルモデル)で共通に使うプロンプト。学習データもこれで作る。"""

from datetime import date

SYSTEM_PROMPT = """あなたは日本語のイベント告知ページから情報を抜き出す係です。
与えられた本文から、次の項目を JSON オブジェクトとして出力してください。

- title: イベント名
- category: live / festival / food / exhibition / other のいずれか
- start_date, end_date: YYYY-MM-DD。1日開催なら両方同じ値
- start_time, end_time: HH:MM の24時間表記
- venue_name: 会場名
- address: 会場の住所
- price: 料金の記述を短く。無料なら「無料」
- organizer: 主催者
- summary: 内容の要約。100文字以内

ルール:
1. 本文に書かれていない情報は推測せず null にする
2. 年が書かれていない日付は「取得日」を基準に決める。取得日より2か月以上前になる場合は翌年とみなす
3. 「8/15(土)」「令和8年8月15日」のような表記も YYYY-MM-DD に直す
4. 複数日程がある場合は最初の日を start_date、最後の日を end_date にする
5. 出力は JSON のみ。説明文は書かない"""


def build_user_message(text: str, fetched_on: date) -> str:
    return f"取得日: {fetched_on.isoformat()}\n\n本文:\n{text}"


def build_messages(text: str, fetched_on: date) -> list[dict[str, str]]:
    """ローカルモデル(chat template)と学習データの両方で使う共通形。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(text, fetched_on)},
    ]
```

- [ ] **ステップ 4: 後処理を実装**

`src/event_parser_llm/postprocess.py`:

```python
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
```

- [ ] **ステップ 5: 通ることを確認**

```bash
uv run pytest -v
```

期待: これまでの全テストが PASS。

- [ ] **ステップ 6: コミット**

```bash
git add src/event_parser_llm/prompt.py src/event_parser_llm/postprocess.py tests/test_postprocess.py
git commit -m "feat: 共通プロンプトと日付・時刻の正規化"
```

### タスク 1.4: Claude バックエンド、パイプライン、CLI

**ファイル:**
- 作成: `src/event_parser_llm/backends/__init__.py`, `src/event_parser_llm/backends/claude.py`, `src/event_parser_llm/pipeline.py`, `src/event_parser_llm/cli.py`
- テスト: `tests/test_cli.py`

**提供するもの:** `get_backend(name) -> Extractor`(`Extractor = Callable[[str, date], dict]`)、`parse_url(url, backend) -> ParseResult`、`parse_text(text, backend, fetched_on=None) -> ParseResult`、`cli.main(argv) -> int`

- [ ] **ステップ 1: 落ちるテストを書く**

`tests/test_cli.py`:

```python
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
```

- [ ] **ステップ 2: 落ちることを確認**

```bash
uv run pytest tests/test_cli.py -v
```

- [ ] **ステップ 3: バックエンドの入口を実装**

`src/event_parser_llm/backends/__init__.py`:

```python
"""抽出バックエンド。どれも「本文と取得日を受け取り、生の dict を返す」関数に統一する。"""

from collections.abc import Callable
from datetime import date

Extractor = Callable[[str, date], dict]


def get_backend(name: str) -> Extractor:
    if name == "claude":
        from .claude import extract
    elif name == "local":
        from .local import extract
    else:
        raise ValueError(f"未知のバックエンド: {name}")
    return extract
```

- [ ] **ステップ 4: Claude バックエンドを実装**

`src/event_parser_llm/backends/claude.py`:

```python
"""教師モデル兼ベースライン: Claude Code をヘッドレスモード(claude -p)で呼ぶ。

API キーではなく Claude Code のログイン(Max プラン)で動く。--json-schema を渡すと
結果 JSON の structured_output にスキーマ検証済みの dict が入る。
"""

import json
import os
import subprocess
from datetime import date

from ..prompt import SYSTEM_PROMPT, build_user_message
from ..schema import event_json_schema

MODEL = os.environ.get("CLAUDE_CODE_MODEL", "opus")
EFFORT = os.environ.get("CLAUDE_CODE_EFFORT", "medium")
TIMEOUT_SEC = 300


def extract(text: str, fetched_on: date) -> dict:
    command = [
        "claude", "-p",
        "--output-format", "json",
        "--json-schema", json.dumps(event_json_schema(), ensure_ascii=False),
        "--system-prompt", SYSTEM_PROMPT,
        "--model", MODEL,
        "--effort", EFFORT,
        "--tools", "",  # ツールを外すと前置きが約 2.2 万→約 7 千トークンに減り、使用量の節約になる
        "--max-turns", "1",
        "--no-session-persistence",
    ]
    proc = subprocess.run(
        command,
        input=build_user_message(text, fetched_on),  # 本文は標準入力で渡す
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SEC,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p が失敗しました (exit {proc.returncode}): {proc.stderr.strip()[-500:]}")
    result = json.loads(proc.stdout)
    if result.get("is_error") or "structured_output" not in result:
        raise RuntimeError(f"構造化出力が得られませんでした: {str(result.get('result', ''))[:300]}")
    return result["structured_output"]
```

`claude` コマンドが PATH にあり、タスク 0.2 のログインが済んでいれば動く。Claude Code の対話セッションの中からこのスクリプトを走らせる場合だけ、環境変数 `CLAUDECODE` を外す必要がある(通常のターミナルからなら不要)。

- [ ] **ステップ 5: パイプラインを実装**

`src/event_parser_llm/pipeline.py`:

```python
"""取得 → 抽出 → 正規化をつなぐ。CLI と HTTP API はこれを呼ぶだけ。"""

import time
from datetime import date

from .backends import get_backend
from .fetch import Page, fetch_url, page_from_text
from .postprocess import finalize
from .schema import ParseResult


def parse_page(page: Page, backend: str) -> ParseResult:
    extract = get_backend(backend)
    started = time.perf_counter()
    raw = extract(page.text, page.fetched_on)
    event = finalize(raw, page.fetched_on)
    return ParseResult(
        event=event,
        source_url=page.url,
        fetched_on=page.fetched_on.isoformat(),
        backend=backend,
        elapsed_sec=round(time.perf_counter() - started, 2),
    )


def parse_url(url: str, backend: str) -> ParseResult:
    return parse_page(fetch_url(url), backend)


def parse_text(text: str, backend: str, fetched_on: date | None = None) -> ParseResult:
    return parse_page(page_from_text(text, fetched_on), backend)
```

- [ ] **ステップ 6: CLI を実装**

`src/event_parser_llm/cli.py`:

```python
"""event-parser parse <URL or ファイル> [--backend claude|local]"""

import argparse
import json
import sys
from pathlib import Path

from .pipeline import parse_text, parse_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="event-parser")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("parse", help="URL またはテキストファイルから JSON を作る")
    p.add_argument("source", help="http(s) で始まる URL、またはテキストファイルのパス")
    p.add_argument("--backend", choices=["claude", "local"], default="local")
    args = parser.parse_args(argv)

    if args.source.startswith(("http://", "https://")):
        result = parse_url(args.source, args.backend)
    else:
        result = parse_text(Path(args.source).read_text(encoding="utf-8"), args.backend)

    json.dump(result.model_dump(), sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0
```

- [ ] **ステップ 7: 通ることを確認**

```bash
uv run pytest -v
```

- [ ] **ステップ 8: 実際に Claude で 1 ページ抽出してみる(スモークテスト)**

タスク 1.2 で使った URL を渡す。

```bash
uv run event-parser parse "ここにURL" --backend claude
```

期待: `event` に妥当な値が入った JSON が出る。`elapsed_sec` と、結果のどこが間違っていたかを journal に書く。ここでの気づき(例: 年の推定、料金の書き方)はプロンプトの改善に使う。プロンプトを直したら、直した理由も journal に書く。

- [ ] **ステップ 9: コミット**

```bash
git add src/event_parser_llm/backends src/event_parser_llm/pipeline.py src/event_parser_llm/cli.py tests/test_cli.py
git commit -m "feat: Claude バックエンドとパイプライン、CLI"
```

### タスク 1.5: HTTP API

**ファイル:**
- 作成: `src/event_parser_llm/api.py`
- テスト: `tests/test_api.py`

**提供するもの:** FastAPI アプリ `app`。`POST /parse`(body: `{"url": ...}` または `{"text": ...}`)、`GET /health`。環境変数 `EVENT_PARSER_BACKEND`(既定 `local`)、`EVENT_PARSER_API_KEY`(設定時は `X-API-Key` ヘッダ必須)

- [ ] **ステップ 1: 落ちるテストを書く**

`tests/test_api.py`:

```python
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
```

- [ ] **ステップ 2: 落ちることを確認**

```bash
uv run pytest tests/test_api.py -v
```

- [ ] **ステップ 3: 実装**

`src/event_parser_llm/api.py`:

```python
"""HTTP API。POST /parse に url か text を渡すと ParseResult を返す。"""

import os

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, model_validator

from .pipeline import parse_text, parse_url
from .schema import ParseResult

app = FastAPI(title="event-parser-llm")

BACKEND = os.environ.get("EVENT_PARSER_BACKEND", "local")
API_KEY = os.environ.get("EVENT_PARSER_API_KEY")


class ParseRequest(BaseModel):
    url: str | None = None
    text: str | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "ParseRequest":
        if bool(self.url) == bool(self.text):
            raise ValueError("url か text のどちらか一方を指定してください")
        return self


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "backend": BACKEND}


@app.post("/parse", response_model=ParseResult, dependencies=[Depends(require_api_key)])
def parse(req: ParseRequest) -> ParseResult:
    try:
        if req.url:
            return parse_url(req.url, BACKEND)
        return parse_text(req.text or "", BACKEND)
    except Exception as e:  # 取得失敗・抽出失敗・検証失敗をまとめて 422 で返す
        raise HTTPException(status_code=422, detail=str(e)) from e
```

- [ ] **ステップ 4: 通ることを確認**

```bash
uv run pytest -v
```

- [ ] **ステップ 5: 手で叩いてみる**

ターミナル 1:

```bash
EVENT_PARSER_BACKEND=claude uv run uvicorn event_parser_llm.api:app --port 8000
```

ターミナル 2:

```bash
curl -s localhost:8000/health
curl -s -X POST localhost:8000/parse -H 'Content-Type: application/json' -d '{"url": "ここにURL"}'
```

- [ ] **ステップ 6: コミットとタグ**

```bash
git add src/event_parser_llm/api.py tests/test_api.py
git commit -m "feat: HTTP API (POST /parse)"
git tag -a v0.1.0 -m "Claude 版パイプライン完成"
git push && git push --tags
```

journal に「フェーズ 1 完了。Claude 版で動くものができた」と、この時点の所感を書く。記事 2 本目の素材になる。

---

## フェーズ 2: データセット構築

### タスク 2.1: URL 収集と本文取得

**ファイル:**
- 作成: `data/urls.csv`, `scripts/collect.py`
- 生成: `data/raw/<id>.txt`(Git 対象外)、`data/manifest.jsonl`(Git 対象)

- [ ] **ステップ 1: 収集方針を決めて journal に書く**

目標 400 件。次のような種類のサイトから、**詳細ページ**(1 ページ 1 イベント)の URL を集める。1 サイトに偏らないように、サイトあたり 10〜20 件まで。

| カテゴリ | 例 |
|---|---|
| live | ライブハウスのスケジュール詳細、ホールの公演情報、音楽フェスの公式サイト |
| festival | 自治体・観光協会の祭り案内、神社の例大祭、商店街のイベント |
| food | ビアガーデン、食フェス、マルシェ、飲食店の期間限定イベント |
| exhibition | 美術館・博物館の展覧会、ギャラリーの企画展、写真展 |
| other | 講演会、ワークショップ、スポーツイベント、フリーマーケット |

集めるときのルール: サイトの利用規約に「スクレイピング禁止」と明記されているものは避ける。本文テキストは手元だけに置き、公開しない(著作物)。

- [ ] **ステップ 2: urls.csv を作る**

`data/urls.csv`(ヘッダ行必須。`category_hint` は自分の見立てで、後のラベル作成の参考にする):

```csv
url,category_hint
https://example.com/events/summer-festival-2026,festival
https://example.com/live/2026-10-01,live
```

最初は 50 件ほどで良い。あとから追記して再実行すれば、未取得分だけ取得する。

- [ ] **ステップ 3: 収集スクリプトを書く**

`scripts/collect.py`:

```python
"""data/urls.csv の URL を取得して本文テキストを data/raw/ に保存し、data/manifest.jsonl に記録する。"""

import csv
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from event_parser_llm.fetch import USER_AGENT, fetch_url

DATA = Path("data")
RAW = DATA / "raw"
MANIFEST = DATA / "manifest.jsonl"
INTERVAL_SEC = 3

_robots: dict[str, RobotFileParser] = {}


def allowed_by_robots(url: str) -> bool:
    parts = urlparse(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin not in _robots:
        rp = RobotFileParser(origin + "/robots.txt")
        try:
            rp.read()
        except Exception:
            rp.allow_all = True  # robots.txt が読めないサイトは許可扱い
        _robots[origin] = rp
    return _robots[origin].can_fetch(USER_AGENT, url)


def page_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:8]


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    done: set[str] = set()
    if MANIFEST.exists():
        done = {json.loads(line)["id"] for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line}

    with (DATA / "urls.csv").open(encoding="utf-8") as f, MANIFEST.open("a", encoding="utf-8") as out:
        for row in csv.DictReader(f):
            url = row["url"].strip()
            pid = page_id(url)
            if pid in done:
                continue
            if not allowed_by_robots(url):
                print(f"skip (robots.txt): {url}", file=sys.stderr)
                continue
            try:
                page = fetch_url(url)
            except Exception as e:
                print(f"fail: {url}: {e}", file=sys.stderr)
                continue
            (RAW / f"{pid}.txt").write_text(page.text, encoding="utf-8")
            entry = {
                "id": pid,
                "url": url,
                "fetched_on": page.fetched_on.isoformat(),
                "category_hint": row.get("category_hint", ""),
                "chars": len(page.text),
            }
            out.write(json.dumps(entry, ensure_ascii=False) + "\n")
            done.add(pid)
            print(f"ok: {pid} {len(page.text)}文字 {url}")
            time.sleep(INTERVAL_SEC)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **ステップ 4: 実行**

```bash
uv run python scripts/collect.py
wc -l data/manifest.jsonl
```

`fail:` や `skip:` になった URL は理由を journal に書く(記事の「取得の難しさ」の素材)。`data/raw/` の数ファイルを開いて、本文が取れているか目視する。取れていないサイトは `urls.csv` から外す。

- [ ] **ステップ 5: コミット**

```bash
git add data/urls.csv data/manifest.jsonl scripts/collect.py
git commit -m "feat: URL 収集スクリプトと最初の収集分"
```

### タスク 2.2: 手作業ラベル(30〜50 件)

**ファイル:**
- 作成: `scripts/make_skeletons.py`, `scripts/validate_labels.py`
- 生成: `data/labels/<id>.json`(Git 対象)

- [ ] **ステップ 1: ひな形生成スクリプト**

`scripts/make_skeletons.py`:

```python
"""ラベル未作成のページに対して、手作業用の空 JSON を data/labels/ に作る。"""

import json
import sys
from pathlib import Path

from event_parser_llm.schema import EventInfo

LABELS = Path("data/labels")
MANIFEST = Path("data/manifest.jsonl")

SKELETON = {name: None for name in EventInfo.model_fields}
SKELETON["title"] = ""
SKELETON["category"] = "other"
SKELETON["summary"] = ""


def main(limit: int) -> int:
    LABELS.mkdir(parents=True, exist_ok=True)
    made = 0
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        pid = json.loads(line)["id"]
        path = LABELS / f"{pid}.json"
        if path.exists():
            continue
        path.write_text(json.dumps(SKELETON, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        made += 1
        if made >= limit:
            break
    print(f"{made} 件のひな形を作りました")
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 40))
```

- [ ] **ステップ 2: 検証スクリプト**

`scripts/validate_labels.py`:

```python
"""data/labels/*.json が EventInfo として妥当か確認する。"""

import json
import sys
from pathlib import Path

from pydantic import ValidationError

from event_parser_llm.schema import EventInfo


def main() -> int:
    files = sorted(Path("data/labels").glob("*.json"))
    bad = 0
    for path in files:
        try:
            EventInfo.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (ValidationError, json.JSONDecodeError) as e:
            bad += 1
            print(f"NG {path.name}: {str(e).splitlines()[0]}")
    print(f"{len(files)} 件中 {bad} 件が不正")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **ステップ 3: ひな形を作り、手で埋める**

```bash
uv run python scripts/make_skeletons.py 40
```

VS Code で `data/raw/<id>.txt` と `data/labels/<id>.json` を左右に並べ、本文を読みながら JSON を埋める。ルールは `prompt.py` の `SYSTEM_PROMPT` と同じ(不明は null、年は取得日基準、summary は 100 文字以内)。

迷ったケースは journal に書く。例: 「開催期間中の休館日はどうする」「複数会場」「料金が複数種類」。この迷いがスキーマとプロンプトの改善点になる。ルールを変えたら `SYSTEM_PROMPT` も直し、既存ラベルも直す。

- [ ] **ステップ 4: 検証**

```bash
uv run python scripts/validate_labels.py
```

期待: `40 件中 0 件が不正`。

- [ ] **ステップ 5: コミット**

```bash
git add scripts/make_skeletons.py scripts/validate_labels.py data/labels
git commit -m "feat: 手作業ラベル 40 件とラベル検証"
```

### タスク 2.3: Claude による下書きとレビュー

**ファイル:**
- 作成: `scripts/draft_labels.py`, `scripts/show.py`
- 生成: `data/drafts/<id>.json`(Git 対象外) → レビュー後 `data/labels/<id>.json` へ移動

- [ ] **ステップ 1: 下書きスクリプト**

`scripts/draft_labels.py`:

```python
"""ラベルも下書きもないページに対して、Claude で下書き JSON を data/drafts/ に作る。"""

import json
import sys
from datetime import date
from pathlib import Path

from event_parser_llm.backends.claude import extract
from event_parser_llm.postprocess import finalize

RAW = Path("data/raw")
LABELS = Path("data/labels")
DRAFTS = Path("data/drafts")
MANIFEST = Path("data/manifest.jsonl")


def main(limit: int) -> int:
    DRAFTS.mkdir(parents=True, exist_ok=True)
    made = 0
    failures = 0
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        entry = json.loads(line)
        pid = entry["id"]
        if (LABELS / f"{pid}.json").exists() or (DRAFTS / f"{pid}.json").exists():
            continue
        text = (RAW / f"{pid}.txt").read_text(encoding="utf-8")
        fetched_on = date.fromisoformat(entry["fetched_on"])
        try:
            event = finalize(extract(text, fetched_on), fetched_on)
        except Exception as e:
            failures += 1
            print(f"fail {pid}: {e}", file=sys.stderr)
            if failures >= 3:
                print("3 連続で失敗したので停止します(使用量の上限に達した可能性)", file=sys.stderr)
                return 1
            continue
        failures = 0
        (DRAFTS / f"{pid}.json").write_text(
            json.dumps(event.model_dump(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        made += 1
        print(f"draft {pid}: {event.title}")
        if made >= limit:
            break
    print(f"{made} 件の下書きを作りました")
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 50))
```

- [ ] **ステップ 2: レビュー用の表示スクリプト**

`scripts/show.py`:

```python
"""本文と下書き(またはラベル)を並べて表示する。 uv run python scripts/show.py <id>"""

import sys
from pathlib import Path


def main(pid: str) -> int:
    print("=" * 30, "本文", "=" * 30)
    print(Path(f"data/raw/{pid}.txt").read_text(encoding="utf-8"))
    for kind in ("drafts", "labels"):
        path = Path(f"data/{kind}/{pid}.json")
        if path.exists():
            print("=" * 30, kind, "=" * 30)
            print(path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
```

- [ ] **ステップ 3: まず 10 件だけ下書きして品質を見る**

```bash
uv run python scripts/draft_labels.py 10
uv run python scripts/show.py <id>
```

下書きの間違いの傾向を journal に書く。頻出する間違いがあれば `SYSTEM_PROMPT` を直す(直したら以降の下書きにだけ効く。前の下書きは手で直す)。

- [ ] **ステップ 4: 残りを 50 件ずつ下書きし、レビューして採用**

```bash
uv run python scripts/draft_labels.py 50
```

1 件ずつ `show.py` で本文と突き合わせ、直すべきところを直してから `data/labels/` に移す。

```bash
# 内容を確認・修正したら
mv data/drafts/<id>.json data/labels/<id>.json
```

レビューは「本文に書かれていないことが入っていないか」「日付の年が合っているか」「category が妥当か」を最優先で見る。
50 件ごとに `/usage` で残量を見る。上限に当たると `claude -p` が失敗し、スクリプトは 3 連続失敗で止まるので、次の 5 時間ウィンドウで再実行する(未処理分だけ続きから作る)。記事用に API 換算額を知りたければ、タスク 0.2 のコマンドを 1 件分の本文で実行して `total_cost_usd` を見る(1 件あたり約 $0.08)。

- [ ] **ステップ 5: 検証とコミット**

```bash
uv run python scripts/validate_labels.py
git add scripts/draft_labels.py scripts/show.py data/labels
git commit -m "feat: Claude 下書き + レビューでラベルを拡充"
```

### タスク 2.4: 学習用データセットの生成

**ファイル:**
- 作成: `scripts/build_dataset.py`
- 生成: `data/dataset/{train,dev,test}.jsonl`(Git 対象外)、`data/split_ids.json`(Git 対象。test の固定用)

- [ ] **ステップ 1: スクリプトを書く**

`scripts/build_dataset.py`:

```python
"""labels と raw から TRL 用(conversational prompt-completion)の train/dev/test jsonl を作る。

一度 test/dev に入った id は data/split_ids.json に記録し、次回以降も同じ分割を保つ。
"""

import json
import random
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from event_parser_llm.prompt import build_messages
from event_parser_llm.schema import EventInfo

RAW = Path("data/raw")
LABELS = Path("data/labels")
MANIFEST = Path("data/manifest.jsonl")
OUT = Path("data/dataset")
SPLIT_IDS = Path("data/split_ids.json")
SEED = 42


def load_examples() -> list[dict]:
    examples = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        entry = json.loads(line)
        pid = entry["id"]
        label_path = LABELS / f"{pid}.json"
        if not label_path.exists():
            continue
        try:
            gold = EventInfo.model_validate(json.loads(label_path.read_text(encoding="utf-8")))
        except ValidationError:
            print(f"skip (invalid label): {pid}", file=sys.stderr)
            continue
        text = (RAW / f"{pid}.txt").read_text(encoding="utf-8")
        fetched_on = date.fromisoformat(entry["fetched_on"])
        gold_dict = gold.model_dump()
        examples.append({
            "id": pid,
            "url": entry["url"],
            "fetched_on": entry["fetched_on"],
            "text": text,
            "gold": gold_dict,
            # ここから下が TRL が読む部分。学習時は prompt と completion だけ残す
            "prompt": build_messages(text, fetched_on),
            "completion": [{"role": "assistant", "content": json.dumps(gold_dict, ensure_ascii=False)}],
        })
    return examples


def split(examples: list[dict]) -> dict[str, list[dict]]:
    previous = json.loads(SPLIT_IDS.read_text(encoding="utf-8")) if SPLIT_IDS.exists() else {}
    assigned = {pid: name for name, ids in previous.items() for pid in ids}
    rng = random.Random(SEED)
    by_category: dict[str, list[dict]] = defaultdict(list)
    for ex in examples:
        by_category[ex["gold"]["category"]].append(ex)

    result: dict[str, list[dict]] = {"train": [], "dev": [], "test": []}
    for items in by_category.values():
        rng.shuffle(items)
        new_items = [ex for ex in items if ex["id"] not in assigned]
        for ex in items:
            if ex["id"] in assigned:
                result[assigned[ex["id"]]].append(ex)
        for i, ex in enumerate(new_items):  # 未割当は 10% test, 10% dev, 80% train
            name = "test" if i % 10 == 0 else "dev" if i % 10 == 1 else "train"
            result[name].append(ex)
    rng.shuffle(result["train"])
    return result


def main() -> int:
    examples = load_examples()
    splits = split(examples)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in splits.items():
        with (OUT / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{name}: {len(rows)} 件")
    SPLIT_IDS.write_text(
        json.dumps({name: sorted(r["id"] for r in rows) for name, rows in splits.items()}, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **ステップ 2: 実行して中身を見る**

```bash
uv run python scripts/build_dataset.py
head -c 1500 data/dataset/train.jsonl
```

`prompt` に system と user、`completion` に assistant の JSON 文字列が入っていることを確認する。

- [ ] **ステップ 3: コミットとタグ**

```bash
git add scripts/build_dataset.py data/split_ids.json
git commit -m "feat: 学習用データセットの生成と分割の固定"
git tag -a v0.2.0 -m "データセット構築完了"
git push && git push --tags
```

journal に件数の内訳(カテゴリ別、手作業/下書き別)、かかった時間、費用を書く。記事 3 本目の素材。

---

## フェーズ 3: ローカル推論基盤とベースライン測定

### タスク 3.1: WSL に llama.cpp をビルド

- [ ] **ステップ 1: ビルド**

```bash
sudo apt-get update && sudo apt-get install -y build-essential cmake git libcurl4-openssl-dev
git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp
cd ~/llama.cpp
cmake -B build
cmake --build build --config Release -j 8 --target llama-server llama-quantize
./build/bin/llama-server --version
```

期待: バージョン(ビルド番号)が表示される。ビルドにかかった時間を journal に書く(VPS では 3 コアなので数倍かかる見込み)。

### タスク 3.2: ベースモデルを GGUF(Q8_0)にする

- [ ] **ステップ 1: 変換用の仮想環境を llama.cpp 側に作る**

```bash
cd ~/llama.cpp
uv venv --python 3.12
uv pip install -r requirements/requirements-convert_hf_to_gguf.txt
```

- [ ] **ステップ 2: HuggingFace からベースモデルを取得**

```bash
cd ~/dev/event-parser-llm
uvx --from huggingface_hub hf download Qwen/Qwen2.5-0.5B-Instruct --local-dir models/hf/qwen2.5-0.5b-instruct
```

- [ ] **ステップ 3: GGUF に変換(q8_0)**

```bash
~/llama.cpp/.venv/bin/python ~/llama.cpp/convert_hf_to_gguf.py models/hf/qwen2.5-0.5b-instruct \
  --outfile models/qwen2.5-0.5b-instruct-q8_0.gguf --outtype q8_0
ls -lh models/*.gguf
```

期待: 約 500〜550MB のファイル。

### タスク 3.3: ローカルバックエンド

**ファイル:**
- 作成: `src/event_parser_llm/backends/local.py`

**提供するもの:** `extract(text, fetched_on) -> dict`。環境変数 `LLAMA_SERVER_URL`(既定 `http://127.0.0.1:8080`)

- [ ] **ステップ 1: llama-server を起動(ターミナル 1)**

```bash
~/llama.cpp/build/bin/llama-server -m models/qwen2.5-0.5b-instruct-q8_0.gguf \
  --host 127.0.0.1 --port 8080 -c 4096 -t 8 -np 1
```

別ターミナルで疎通確認:

```bash
curl -s localhost:8080/health
```

- [ ] **ステップ 2: 実装**

`src/event_parser_llm/backends/local.py`:

```python
"""生徒モデル: llama-server(llama.cpp) を OpenAI 互換 API で呼ぶ。JSON Schema で出力を文法制約する。"""

import json
import os
from datetime import date

import httpx

from ..prompt import build_messages
from ..schema import event_json_schema

BASE_URL = os.environ.get("LLAMA_SERVER_URL", "http://127.0.0.1:8080")


def extract(text: str, fetched_on: date) -> dict:
    payload = {
        "messages": build_messages(text, fetched_on),
        "response_format": {"type": "json_schema", "schema": event_json_schema()},
        "temperature": 0,
        "max_tokens": 512,
    }
    # 接続は 5 秒で諦める(サーバ未起動のときに 5 分待たないため)。応答は 300 秒まで待つ
    timeout = httpx.Timeout(300.0, connect=5.0)
    response = httpx.post(f"{BASE_URL}/v1/chat/completions", json=payload, timeout=timeout)
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return json.loads(content)
```

`response_format` の形は llama.cpp のサーバ README に載っている `{"type": "json_schema", "schema": {...}}`。もし手元のバージョンでエラーになったら `{"type": "json_object", "schema": {...}}` に変えて試す。

- [ ] **ステップ 3: 素の 0.5B で 1 件抽出してみる**

```bash
uv run event-parser parse data/raw/<id>.txt --backend local
```

期待: JSON としては必ず妥当(文法制約のおかげ)だが、中身はかなり間違っているはず。何秒かかったか、どの項目が間違ったかを journal に書く。これが記事 4 本目の「学習前」の姿。

- [ ] **ステップ 4: テストとコミット**

```bash
uv run pytest -v
git add src/event_parser_llm/backends/local.py
git commit -m "feat: llama-server バックエンド(JSON Schema で文法制約)"
```

### タスク 3.4: 評価スクリプトとベースライン測定

**ファイル:**
- 作成: `src/event_parser_llm/metrics.py`, `scripts/evaluate.py`
- テスト: `tests/test_metrics.py`
- 生成: `results/<name>.json`(Git 対象)

**提供するもの:** `CORE_FIELDS`, `ALL_FIELDS`, `compare(pred, gold) -> dict[str, bool]`, `summarize(results) -> dict[str, float]`

- [ ] **ステップ 1: 落ちるテストを書く**

`tests/test_metrics.py`:

```python
from event_parser_llm.metrics import compare, summarize

GOLD = {
    "title": "ABC夏祭り", "category": "festival",
    "start_date": "2026-08-15", "end_date": "2026-08-15",
    "start_time": "17:00", "end_time": "21:00",
    "venue_name": "中央公園", "address": "東京都千代田区1-1",
    "price": "無料", "organizer": "ABC商店街振興組合",
}


def test_exact_and_loose_matching():
    pred = {**GOLD, "title": "ＡＢＣ夏祭り", "address": "千代田区1-1", "end_time": "20:00"}
    r = compare(pred, GOLD)
    assert r["title"] is True      # 全角半角の差は無視
    assert r["address"] is True    # 住所は包含で正解
    assert r["end_time"] is False


def test_summarize_reports_core_all_correct():
    results = [compare(GOLD, GOLD), compare({**GOLD, "start_date": None}, GOLD)]
    s = summarize(results)
    assert s["start_date"] == 0.5
    assert s["core_all_correct"] == 0.5
```

- [ ] **ステップ 2: 落ちることを確認**

```bash
uv run pytest tests/test_metrics.py -v
```

- [ ] **ステップ 3: 指標を実装**

`src/event_parser_llm/metrics.py`:

```python
"""予測と正解を項目ごとに比較する。評価スクリプトと Colab の両方から使う。"""

import unicodedata

CORE_FIELDS = ["title", "category", "start_date", "end_date", "start_time", "venue_name"]
LOOSE_FIELDS = ["address", "price", "organizer"]
ALL_FIELDS = CORE_FIELDS + ["end_time"] + LOOSE_FIELDS


def _norm(value) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).replace(" ", "").lower()


def field_match(field: str, pred, gold) -> bool:
    p, g = _norm(pred), _norm(gold)
    if field in LOOSE_FIELDS:
        # 表記ゆれが大きい項目は「片方がもう片方を含む」で正解扱い
        return p == g or (bool(p) and bool(g) and (p in g or g in p))
    return p == g


def compare(pred: dict, gold: dict) -> dict[str, bool]:
    return {field: field_match(field, pred.get(field), gold.get(field)) for field in ALL_FIELDS}


def summarize(results: list[dict[str, bool]]) -> dict[str, float]:
    n = len(results)
    if n == 0:
        return {}
    summary = {field: sum(r[field] for r in results) / n for field in ALL_FIELDS}
    summary["core_all_correct"] = sum(all(r[f] for f in CORE_FIELDS) for r in results) / n
    return summary
```

- [ ] **ステップ 4: 通ることを確認**

```bash
uv run pytest tests/test_metrics.py -v
```

- [ ] **ステップ 5: 評価スクリプト**

`scripts/evaluate.py`:

```python
"""test(または dev)セットに対してバックエンドを実行し、項目別正解率と応答時間を results/ に出す。"""

import argparse
import json
import statistics
import sys
import time
from datetime import date
from pathlib import Path

from event_parser_llm.metrics import CORE_FIELDS, compare, summarize
from event_parser_llm.pipeline import parse_text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["claude", "local"], required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--name", required=True, help="結果ファイル名。例: base-0.5b, lora-v1, claude")
    ap.add_argument("--limit", type=int, default=0, help="先頭 N 件だけ評価(0 は全件)")
    args = ap.parse_args()

    rows = [
        json.loads(line)
        for line in Path(f"data/dataset/{args.split}.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    if args.limit:
        rows = rows[: args.limit]

    results, times, details, valid = [], [], [], 0
    for row in rows:
        started = time.perf_counter()
        try:
            pred = parse_text(row["text"], args.backend, date.fromisoformat(row["fetched_on"])).event.model_dump()
            valid += 1
        except Exception as e:
            pred = {}
            print(f"fail {row['id']}: {e}", file=sys.stderr)
        elapsed = time.perf_counter() - started
        times.append(elapsed)
        match = compare(pred, row["gold"])
        results.append(match)
        details.append({"id": row["id"], "elapsed_sec": round(elapsed, 2), "pred": pred, "gold": row["gold"], "match": match})
        core_ok = all(match[f] for f in CORE_FIELDS)
        print(f"{row['id']} {elapsed:6.1f}s core_ok={core_ok}")

    summary = summarize(results)
    summary["json_valid_rate"] = valid / len(rows)
    summary["latency_median_sec"] = round(statistics.median(times), 2)
    summary["latency_max_sec"] = round(max(times), 2)

    Path("results").mkdir(exist_ok=True)
    out = Path(f"results/{args.name}.json")
    out.write_text(json.dumps({"summary": summary, "details": details}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\n| 指標 | 値 |\n|---|---|")
    for key, value in summary.items():
        print(f"| {key} | {value:.3f} |")
    print(f"\n書き出し: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **ステップ 6: 素の 0.5B を test セットで測る(llama-server 起動中に)**

```bash
uv run python scripts/evaluate.py --backend local --name base-0.5b
```

- [ ] **ステップ 7: Claude を test セットで測る**

```bash
uv run python scripts/evaluate.py --backend claude --name claude
```

注意: test セットのラベルの多くは Claude の下書きを人が直したものなので、Claude に有利な評価になる。この偏りは記事で正直に書く。

- [ ] **ステップ 8: 結果を記録してコミット、タグ**

2 つの表を journal に貼る。

```bash
git add src/event_parser_llm/metrics.py scripts/evaluate.py tests/test_metrics.py results/
git commit -m "feat: 評価スクリプトとベースライン(素の 0.5B / Claude)"
git tag -a v0.3.0 -m "ローカル推論基盤とベースライン"
git push && git push --tags
```

---

## フェーズ 4: LoRA 学習と量子化

### タスク 4.1: Colab で LoRA 学習

**ファイル:**
- 作成: `notebooks/train_lora.ipynb`(Colab から「ファイル > ダウンロード > .ipynb」で保存し、リポジトリに入れる)

- [ ] **ステップ 1: データを Google Drive に置く**

Google Drive に `event-parser-llm/dataset/` フォルダを作り、`data/dataset/train.jsonl` と `dev.jsonl` をアップロードする。

- [ ] **ステップ 2: Colab で新規ノートブックを作り、ランタイムを T4 GPU にする**

「ランタイム > ランタイムのタイプを変更 > T4 GPU」。

- [ ] **ステップ 3: セル 1: インストール**

```python
!pip install -q -U "trl>=0.20" peft transformers datasets accelerate
!pip install -q "git+https://github.com/<あなたのGitHubユーザー名>/event-parser-llm.git@v0.3.0"
import trl, transformers, peft
print(trl.__version__, transformers.__version__, peft.__version__)
```

バージョンを journal に書く(再現性のため)。

- [ ] **ステップ 4: セル 2: Drive をマウント**

```python
from google.colab import drive
drive.mount("/content/drive")
WORK = "/content/drive/MyDrive/event-parser-llm"
!mkdir -p {WORK}/runs
!ls {WORK}/dataset
```

- [ ] **ステップ 5: セル 3: データセットを読む**

```python
from datasets import load_dataset

ds = load_dataset("json", data_files={"train": f"{WORK}/dataset/train.jsonl", "dev": f"{WORK}/dataset/dev.jsonl"})
# TRL に渡すのは prompt と completion だけ(他の列は評価用)
ds_train = ds["train"].select_columns(["prompt", "completion"])
ds_dev = ds["dev"].select_columns(["prompt", "completion"])
print(len(ds_train), len(ds_dev))
print(ds_train[0]["completion"][0]["content"][:200])
```

- [ ] **ステップ 6: セル 4: 学習**

```python
import torch
from peft import LoraConfig
from transformers import AutoTokenizer
from trl import SFTConfig, SFTTrainer

BASE = "Qwen/Qwen2.5-0.5B-Instruct"
RUN = f"{WORK}/runs/lora-v1"

tokenizer = AutoTokenizer.from_pretrained(BASE)

lora = LoraConfig(
    r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
)

cfg = SFTConfig(
    output_dir=RUN,
    model_init_kwargs={"dtype": torch.float32},  # T4 は bf16 非対応。0.5B なら fp32 で十分載る
    bf16=False, fp16=False,                       # SFTConfig は既定で bf16=True になるので明示的に切る
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,                # 実効バッチ 8
    num_train_epochs=3,
    learning_rate=1e-4,
    lr_scheduler_type="cosine",
    warmup_steps=10,
    max_length=3072,                              # 本文 3000 文字 + プロンプト + JSON が収まる長さ
    completion_only_loss=True,                    # assistant の JSON 部分だけに損失をかける
    logging_steps=5,
    eval_strategy="epoch",
    save_strategy="epoch",
    save_total_limit=2,
    report_to="none",
    seed=42,
)

trainer = SFTTrainer(
    model=BASE, args=cfg,
    train_dataset=ds_train, eval_dataset=ds_dev,
    processing_class=tokenizer, peft_config=lora,
)
trainer.train()
trainer.save_model(f"{RUN}/adapter")
```

学習ログの `loss` と `eval_loss` がエポックごとに下がることを確認し、スクリーンショットを撮る。所要時間も記録する。
セッションが切れたら、同じセルで `trainer.train(resume_from_checkpoint=True)` にして再開する。

- [ ] **ステップ 7: セル 5: dev セットで簡易評価(文法制約なし)**

```python
import json
from datetime import date

from event_parser_llm.metrics import compare, summarize
from event_parser_llm.postprocess import finalize
from event_parser_llm.prompt import build_messages

model = trainer.model
model.eval()


def predict(text: str, fetched_on: str) -> dict:
    messages = build_messages(text, date.fromisoformat(fetched_on))
    prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=512, do_sample=False)
    generated = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return json.loads(generated)


results, invalid = [], 0
for row in ds["dev"]:
    try:
        pred = finalize(predict(row["text"], row["fetched_on"]), date.fromisoformat(row["fetched_on"])).model_dump()
    except Exception as e:
        pred, invalid = {}, invalid + 1
        print("invalid:", row["id"], str(e)[:80])
    results.append(compare(pred, row["gold"]))

summary = summarize(results)
summary["json_valid_rate"] = 1 - invalid / len(ds["dev"])
for k, v in summary.items():
    print(f"{k:20s} {v:.3f}")
```

ここでは文法制約がないので JSON が壊れることがある。壊れた割合(`json_valid_rate`)そのものが「文法制約の価値」を示す数字になる。

- [ ] **ステップ 8: セル 6: 合成して fp16 で保存**

```python
merged = trainer.model.merge_and_unload()
merged = merged.to(torch.float16)
merged.save_pretrained(f"{RUN}/merged", safe_serialization=True)
tokenizer.save_pretrained(f"{RUN}/merged")
!ls -lh {RUN}/merged
```

- [ ] **ステップ 9: セル 7: GGUF(q8_0)に変換**

```python
!git clone --depth 1 https://github.com/ggml-org/llama.cpp /content/llama.cpp
!python /content/llama.cpp/convert_hf_to_gguf.py {RUN}/merged \
  --outfile {RUN}/event-parser-0.5b-v1-q8_0.gguf --outtype q8_0
!ls -lh {RUN}/*.gguf
```

`ModuleNotFoundError` が出た場合は、足りないモジュール名を `!pip install -q <名前>` で入れて再実行する。

- [ ] **ステップ 10: ノートブックを保存してコミット**

Colab の「ファイル > ダウンロード > .ipynb」で `notebooks/train_lora.ipynb` として保存する。`<あなたのGitHubユーザー名>` を含むセルはそのままで良い。

```bash
git add notebooks/train_lora.ipynb
git commit -m "feat: Colab での LoRA 学習ノートブック"
```

### タスク 4.2: 学習後モデルを WSL で評価

- [ ] **ステップ 1: GGUF を手元に持ってくる**

Google Drive の Web 画面から `event-parser-0.5b-v1-q8_0.gguf` をダウンロードし、`~/dev/event-parser-llm/models/` に置く。

- [ ] **ステップ 2: llama-server を学習後モデルで起動(ターミナル 1)**

```bash
~/llama.cpp/build/bin/llama-server -m models/event-parser-0.5b-v1-q8_0.gguf \
  --host 127.0.0.1 --port 8080 -c 4096 -t 8 -np 1
```

- [ ] **ステップ 3: test セットで評価**

```bash
uv run python scripts/evaluate.py --backend local --name lora-v1
```

`results/base-0.5b.json`、`results/claude.json` と並べて表にし、journal に書く。

- [ ] **ステップ 4: 結果を見て次の一手を決める**

| 状況 | 次の一手 |
|---|---|
| コア全項目正解率が Claude の 7 割以上 | このまま VPS へ(フェーズ 5) |
| 特定の項目だけ悪い | その項目の誤り例を `results/lora-v1.json` の `details` から 10 件見て、ラベルの揺れかプロンプトの曖昧さかを切り分け、直して再学習(lora-v2) |
| 全体的に悪い | データを 100 件増やして再学習。それでも駄目なら `BASE` を `Qwen/Qwen2.5-1.5B-Instruct` に変え、量子化を Q4_K_M に(`--outtype f16` で変換後、`llama-quantize in.gguf out.gguf Q4_K_M`) |

- [ ] **ステップ 5: コミットとタグ**

```bash
git add results/
git commit -m "docs: LoRA v1 の評価結果"
git tag -a v0.4.0 -m "LoRA 学習と量子化"
git push && git push --tags
```

---

## フェーズ 5: VPS デプロイ

### タスク 5.1: VPS の初期設定

**ファイル:**
- 作成: `deploy/setup_vps.sh`

前提: Ubuntu 22.04 または 24.04。sudo が使えるユーザーで SSH 接続できること。

- [ ] **ステップ 1: セットアップスクリプトを書く**

`deploy/setup_vps.sh`:

```bash
#!/usr/bin/env bash
# VPS の初期設定。sudo 権限のあるユーザーで実行する: bash deploy/setup_vps.sh <GitHubユーザー名>
set -euo pipefail

GITHUB_USER="${1:?GitHub ユーザー名を指定してください}"

echo "== パッケージ"
sudo apt-get update
sudo apt-get install -y build-essential cmake git curl libcurl4-openssl-dev ufw htop

echo "== スワップ 2GB(メモリ 2GB の保険)"
if ! sudo swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

echo "== ファイアウォール(SSH と API のみ)"
sudo ufw allow 22/tcp
sudo ufw allow 8000/tcp
sudo ufw --force enable

echo "== アプリ用ユーザー"
id app >/dev/null 2>&1 || sudo useradd -m -s /bin/bash app

echo "== llama.cpp をビルド(3 コアなので 10〜20 分かかる)"
sudo -u app bash -c '
  set -e
  cd ~
  [ -d llama.cpp ] || git clone https://github.com/ggml-org/llama.cpp
  cd llama.cpp
  cmake -B build
  cmake --build build --config Release -j 2 --target llama-server
'

echo "== uv とアプリ"
sudo -u app bash -c '
  set -e
  curl -LsSf https://astral.sh/uv/install.sh | sh
  cd ~
  [ -d event-parser-llm ] || git clone https://github.com/'"$GITHUB_USER"'/event-parser-llm.git
  cd event-parser-llm
  ~/.local/bin/uv sync --no-dev
  mkdir -p models
'

echo "== 完了。次: GGUF を /home/app/event-parser-llm/models/ に置き、.env を作り、systemd ユニットを入れる"
```

- [ ] **ステップ 2: VPS に送って実行**

```bash
scp deploy/setup_vps.sh <ユーザー>@<VPSのIP>:~/
ssh <ユーザー>@<VPSのIP> 'bash ~/setup_vps.sh <GitHubユーザー名>'
```

ビルド時間と `free -m` の結果を journal に書く。

- [ ] **ステップ 3: コミット**

```bash
git add deploy/setup_vps.sh
git commit -m "feat: VPS セットアップスクリプト"
```

### タスク 5.2: systemd で常駐させる

**ファイル:**
- 作成: `deploy/llama-server.service`, `deploy/event-parser-api.service`

- [ ] **ステップ 1: ユニットファイルを書く**

`deploy/llama-server.service`:

```ini
[Unit]
Description=llama.cpp server (event-parser)
After=network.target

[Service]
User=app
WorkingDirectory=/home/app/event-parser-llm
ExecStart=/home/app/llama.cpp/build/bin/llama-server \
  -m /home/app/event-parser-llm/models/event-parser-0.5b-v1-q8_0.gguf \
  --host 127.0.0.1 --port 8080 -c 4096 -t 3 -np 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`deploy/event-parser-api.service`:

```ini
[Unit]
Description=event-parser HTTP API
After=network.target llama-server.service
Requires=llama-server.service

[Service]
User=app
WorkingDirectory=/home/app/event-parser-llm
EnvironmentFile=/home/app/event-parser-llm/.env
ExecStart=/home/app/event-parser-llm/.venv/bin/uvicorn event_parser_llm.api:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

- [ ] **ステップ 2: コミットして push(VPS 側で pull するため)**

```bash
git add deploy/
git commit -m "feat: systemd ユニット"
git push
```

- [ ] **ステップ 3: モデルと .env を VPS に置く**

```bash
scp models/event-parser-0.5b-v1-q8_0.gguf <ユーザー>@<VPSのIP>:/tmp/
ssh <ユーザー>@<VPSのIP>
# 以下 VPS 上
sudo mv /tmp/event-parser-0.5b-v1-q8_0.gguf /home/app/event-parser-llm/models/
sudo chown app:app /home/app/event-parser-llm/models/*.gguf
sudo -u app bash -c 'cd ~/event-parser-llm && git pull && printf "EVENT_PARSER_BACKEND=local\nEVENT_PARSER_API_KEY=%s\n" "$(openssl rand -hex 16)" > .env && cat .env'
```

表示された `EVENT_PARSER_API_KEY` を控える。

- [ ] **ステップ 4: ユニットを有効化**

```bash
sudo cp /home/app/event-parser-llm/deploy/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now llama-server event-parser-api
sudo systemctl status llama-server event-parser-api --no-pager
```

期待: 両方 `active (running)`。失敗したら `sudo journalctl -u llama-server -n 50 --no-pager` でログを見る。

### タスク 5.3: 動作確認と計測

- [ ] **ステップ 1: VPS 上で確認**

```bash
curl -s localhost:8080/health
curl -s localhost:8000/health
free -m
```

`free -m` の `used` と `available` を journal に書く。

- [ ] **ステップ 2: 手元から叩く**

```bash
time curl -s -X POST http://<VPSのIP>:8000/parse \
  -H 'Content-Type: application/json' -H 'X-API-Key: <控えた鍵>' \
  -d '{"url": "ここにURL"}'
```

`elapsed_sec` と `time` の実測を journal に書く。設計書の見積り(20〜30 秒)と比べる。

- [ ] **ステップ 3: 負荷中のメモリを見る**

ターミナル 1 で `htop`(または `watch -n1 free -m`)を開いたまま、ターミナル 2 で上の curl を実行し、ピーク時の使用量を記録する。スクリーンショットを撮る。

- [ ] **ステップ 4: 再起動耐性**

```bash
sudo reboot
# 1〜2 分後
curl -s http://<VPSのIP>:8000/health
```

- [ ] **ステップ 5: タグ**

```bash
git tag -a v0.5.0 -m "2GB VPS で稼働"
git push --tags
```

更新手順(以後モデルやコードを変えたとき):

```bash
# VPS 上
sudo -u app bash -c 'cd ~/event-parser-llm && git pull && ~/.local/bin/uv sync --no-dev'
sudo systemctl restart llama-server event-parser-api
```

---

## フェーズ 6: 比較評価と記事化

### タスク 6.1: 3 者比較表を作る

- [ ] **ステップ 1: `results/*.json` の summary から表を作る**

```bash
uv run python - <<'EOF'
import json
from pathlib import Path
names = ["base-0.5b", "lora-v1", "claude"]
data = {n: json.loads(Path(f"results/{n}.json").read_text())["summary"] for n in names if Path(f"results/{n}.json").exists()}
keys = list(next(iter(data.values())).keys())
print("| 指標 | " + " | ".join(data) + " |")
print("|---|" + "---|" * len(data))
for k in keys:
    print(f"| {k} | " + " | ".join(f"{data[n][k]:.3f}" for n in data) + " |")
EOF
```

- [ ] **ステップ 2: `docs/results.md` に貼ってコミット**

VPS での応答時間とメモリ使用量も同じファイルに書く。

```bash
git add docs/results.md
git commit -m "docs: 3 者比較の結果"
git push
```

### タスク 6.2: Zenn 記事

Zenn の Web エディタで書く。各記事の冒頭に、対応するタグ(`v0.1.0` など)へのリンクを置く。

| # | タイトル案 | 主な素材 |
|---|---|---|
| 1 | 2GB VPS で動く「イベント情報抽出 LLM」を自作する: 構想と設計 | 設計書、なぜ 0.5B + LoRA か、スキーマ |
| 2 | まず Claude で動くものを作る: Max プランの Claude Code をヘッドレスで呼ぶ | フェーズ 1 の journal、`--json-schema`、プロンプト改善の経緯 |
| 3 | 教師データを 400 件作った話: 手作業 40 件と Claude 下書きのレビュー | 迷ったケース、費用、時間 |
| 4 | llama.cpp で素の Qwen2.5-0.5B を動かし、文法制約で JSON を強制する | ベースライン結果、文法制約の効果 |
| 5 | Colab 無料枠で LoRA 学習して GGUF にするまで | loss、dev 評価、bf16 の罠 |
| 6 | 2GB VPS に systemd で載せる: メモリと応答時間の実測 | `free -m`、`htop`、実測値 |
| 7 | 3 者比較とまとめ: 自作 0.5B は Claude にどこまで迫れたか | `docs/results.md`、失敗談、次の一手 |

各記事は「やったこと → 結果の数字 → 想定と違ったこと → 次に何を変えるか」の順で書くと、journal からほぼそのまま起こせる。

---

## 自己レビュー(この手順書の確認)

- 設計書の各節に対応するタスク: 5 節スキーマ → 1.1、6 節コンポーネント → 1.2〜1.5 と 3.3〜3.4、7 節モデル → 3.1〜3.2 と 5.2、8 節学習 → 4.1、9 節データ → 2.1〜2.4、10 節評価 → 3.4 と 4.2 と 6.1、11 節デプロイ → 5.1〜5.3、14 節運用 → 各フェーズ末尾のタグと 6.2
- 名前の整合: `get_backend` / `finalize` / `build_messages` / `event_json_schema` / `parse_text(text, backend, fetched_on)` / `CORE_FIELDS` はすべて定義したタスクと同じ名前で参照している
- 外部仕様の確認済み事項: Claude Code 2.1.258 の `claude -p --json-schema` が `structured_output` を返すこと(実際に呼んで確認)、llama-server の `response_format` の形、TRL の prompt-completion 形式と `completion_only_loss`、`SFTConfig` の `bf16` 既定値
