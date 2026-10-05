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
