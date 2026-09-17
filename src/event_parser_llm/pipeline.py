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
