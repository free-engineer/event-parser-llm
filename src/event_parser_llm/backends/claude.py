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
