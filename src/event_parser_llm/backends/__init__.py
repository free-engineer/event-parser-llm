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
