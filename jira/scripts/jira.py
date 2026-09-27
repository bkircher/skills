#!/usr/bin/env python3
"""Search, read, update, and create Jira issues through one command interface."""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from client import JiraClient
from issues import JiraIssues


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    search = commands.add_parser("search", help="Search issues with filters or JQL")
    search.add_argument("--text")
    search.add_argument("--project")
    search.add_argument("--assignee", help="Use me or an account ID")
    search.add_argument("--open", action="store_true", dest="open_only")
    search.add_argument("--jql")
    search.add_argument("--fields", type=_fields)
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--page-token", help="Continue the same query with its returned cursor")

    get = commands.add_parser("get", help="Read one issue, selected fields, and optional comments")
    get.add_argument("issue", help="One issue key or HTTPS browse URL")
    get.add_argument("--fields", type=_fields)
    get.add_argument("--comments", action="store_true")
    get.add_argument("--comments-only", action="store_true", help="Read comments without an issue-fields request")
    get.add_argument("--comment-limit", type=int, default=20)
    get.add_argument("--comment-start", type=int, default=0)
    get.add_argument("--acceptance-criteria", action="store_true", help="Discover exact-name custom fields on demand")
    get.add_argument("--acceptance-field", help="Read a known custom field without discovery")
    get.add_argument("--for-update", action="store_true", help="Return a snapshot for freshness checks")
    get.add_argument("--raw-adf", action="store_true", help="Also return original rich-text documents")

    update = commands.add_parser("update", help="Update one issue and verify the saved fields")
    update.add_argument("issue")
    update.add_argument("--input", required=True, help="JSON file, or - for stdin")
    update.add_argument("--preview", action="store_true", help="Read and validate, but do not write")

    create = commands.add_parser("create", help="Create one issue and verify the saved fields")
    create.add_argument("--input", required=True, help="JSON file, or - for stdin")
    create.add_argument("--preview", action="store_true", help="Read metadata and validate, but do not write")

    metadata = commands.add_parser("metadata", help="Read field IDs, types, requirements, and allowed values")
    target = metadata.add_mutually_exclusive_group(required=True)
    target.add_argument("--issue", help="Get editable fields for one issue")
    target.add_argument("--project", help="Get issue types for a project")
    target.add_argument("--fields", action="store_true", help="List site field definitions")
    metadata.add_argument("--issue-type", help="With --project, get create fields for this type name or ID")
    return root


def main(argv: list[str] | None = None) -> int:
    argument_parser = parser()
    args = argument_parser.parse_args(argv)
    if args.command == "metadata" and args.issue_type and not args.project:
        argument_parser.error("--issue-type requires --project")
    if args.command == "get" and args.comments_only and any((
        args.fields is not None, args.for_update, args.acceptance_criteria, args.acceptance_field,
    )):
        argument_parser.error("--comments-only cannot be combined with issue field options")
    try:
        # Validate local input before loading credentials or making any API request.
        spec = _load_input(args.input) if args.command in {"update", "create"} else None
        service = JiraIssues(JiraClient.from_env())
        result = _run(service, args, spec)
    except (ValueError, OSError, RuntimeError) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 2 if isinstance(error, ValueError) else 1
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if result.get("status") in {"unknown", "unverified"}:
        return 3
    if result.get("status") in {"rejected", "conflict"}:
        return 1
    return 0


def _run(service: JiraIssues, args: argparse.Namespace, spec: Any) -> dict[str, Any]:
    if args.command == "search":
        return service.search(jql=args.jql, text=args.text, project=args.project,
                              assignee=args.assignee, open_only=args.open_only,
                              fields=args.fields, limit=args.limit, page_token=args.page_token)
    if args.command == "get":
        if args.comments_only:
            key = service.issue_key(args.issue)
            return {"key": key, "url": f"{service.client.base_url}/browse/{key}",
                    "comments": service.comments(key, limit=args.comment_limit,
                                                  start=args.comment_start, raw_adf=args.raw_adf)}
        return service.get(args.issue, fields=args.fields, comments=args.comments,
                           comment_limit=args.comment_limit, comment_start=args.comment_start,
                           acceptance_criteria=args.acceptance_criteria,
                           acceptance_field=args.acceptance_field,
                           for_update=args.for_update, raw_adf=args.raw_adf)
    if args.command == "update":
        return service.update(args.issue, spec, preview=args.preview)
    if args.command == "create":
        return service.create(spec, preview=args.preview)
    if args.issue:
        key = service.issue_key(args.issue)
        return {"issue": key, "fields": service.metadata.for_edit(key)}
    if args.fields:
        return {"fields": service.metadata.fields()}
    if args.issue_type:
        return service.metadata.for_create(args.project, args.issue_type)
    return {"project": args.project, "issue_types": service.metadata.issue_types(args.project)}


def _fields(value: str) -> list[str]:
    return [field.strip() for field in value.split(",")]


def _load_input(name: str) -> dict[str, Any]:
    raw = sys.stdin.read() if name == "-" else Path(name).read_text(encoding="utf-8")
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object,
                           parse_constant=_invalid_constant, parse_float=_finite_float)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid input JSON at line {error.lineno}, column {error.colno}") from None
    if not isinstance(value, dict):
        raise ValueError("Input must be one JSON object, not a list of issues")
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
