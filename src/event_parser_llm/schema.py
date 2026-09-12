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