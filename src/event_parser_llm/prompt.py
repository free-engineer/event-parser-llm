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
