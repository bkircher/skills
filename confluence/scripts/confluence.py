#!/usr/bin/env python3
"""Search, read, create, and update Confluence Cloud pages."""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from client import ConfluenceClient
from pages import ConfluencePages


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    search = commands.add_parser("search", help="Find pages by text, optionally in a space")
    search.add_argument("query")
    search.add_argument("--space", help="Space key")
    search.add_argument("--limit", type=int, default=10)

    get = commands.add_parser("get", help="Read one page by ID or URL")
    get.add_argument("page")
    get.add_argument("--children", action="store_true")
    get.add_argument("--raw-adf", action="store_true")
    get.add_argument("--for-update", action="store_true")

    create = commands.add_parser("create", help="Create one published page")
    create.add_argument("--input", required=True, help="JSON file, or - for stdin")
    create.add_argument("--preview", action="store_true", help="Validate locally without writing")

    update = commands.add_parser("update", help="Update one page with a version check")
    update.add_argument("page")
    update.add_argument("--input", required=True, help="JSON file, or - for stdin")
    update.add_argument("--preview", action="store_true", help="Read and validate without writing")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        spec = _load_input(args.input) if args.command in {"create", "update"} else None
        pages = ConfluencePages(ConfluenceClient.from_env())
        if args.command == "search":
            result = pages.search(args.query, space=args.space, limit=args.limit)
        elif args.command == "get":
            result = pages.get(args.page, children=args.children, raw_adf=args.raw_adf,
                               for_update=args.for_update)
        elif args.command == "create":
            result = pages.create(spec, preview=args.preview)
        else:
            result = pages.update(args.page, spec, preview=args.preview)
    except (ValueError, OSError, RuntimeError) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 2 if isinstance(error, ValueError) else 1
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if result.get("status") in {"unknown", "unverified"}:
        return 3
    if result.get("status") in {"rejected", "conflict"}:
        return 1
    return 0


def _load_input(name: str) -> dict[str, Any]:
    raw = sys.stdin.read() if name == "-" else Path(name).read_text(encoding="utf-8")
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object,
                           parse_constant=_invalid_constant, parse_float=_finite_float)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid input JSON at line {error.lineno}, column {error.colno}") from None
    if not isinstance(value, dict):
        raise ValueError("Input must be one JSON object, not a list of pages")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Input JSON contains a duplicate key")
        result[key] = value
    return result


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        _invalid_constant(value)
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError("Input JSON must not contain non-finite numbers")


if __name__ == "__main__":
    raise SystemExit(main())
