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
    return Page(
        url=None, text=normalize_text(text), fetched_on=fetched_on or date.today()
    )
