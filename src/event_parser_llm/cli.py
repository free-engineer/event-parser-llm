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
