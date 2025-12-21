#!/usr/bin/env python3
"""
Fetch all comments from a Jira ticket.

Usage:
  python fetch_comments.py ABC-123 | jq
  python fetch_comments.py https://example.atlassian.net/browse/ABC-123 | jq
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from jira import render_markdown


ISSUE_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"Missing environment variable: {name}", file=sys.stderr)
        raise SystemExit(2)
    return value


def _load_auth() -> str:
    email = _require_env("ATLASSIAN_EMAIL")
    token = _require_env("ATLASSIAN_API_TOKEN")
    creds = f"{email}:{token}".encode("utf-8")
    return "Basic " + base64.b64encode(creds).decode("utf-8")


def _request_json(method: str, url: str, auth_header: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "Authorization": auth_header},
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} for {url}\n{err_body}") from e

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse JSON from {url}: {e}\nRaw:\n{raw}") from e


def _extract_issue_key(value: str) -> str:
    match = ISSUE_KEY_RE.search(value)
    if not match:
        raise ValueError(f"Could not find a Jira issue key in: {value}")
    return match.group(1)


def fetch_comments(base_url: str, auth_header: str, issue_key: str) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    start_at = 0
    max_results = 100
    encoded_key = urllib.parse.quote(issue_key)

    while True:
        url = (
            f"{base_url}/rest/api/3/issue/{encoded_key}/comment"
            f"?startAt={start_at}&maxResults={max_results}"
        )
        data = _request_json("GET", url, auth_header)
        for comment in data.get("comments") or []:
            author = comment.get("author") or {}
            comments.append(
                {
                    "id": comment.get("id"),
                    "author": {
                        "displayName": author.get("displayName"),
                        "accountId": author.get("accountId"),
                    },
                    "created": comment.get("created"),
                    "updated": comment.get("updated"),
                    "body_markdown": render_markdown(comment.get("body")),
                }
            )

        total = data.get("total")
        start_at = data.get("startAt", start_at)
        max_results = data.get("maxResults", max_results)

        if total is None or start_at + max_results >= total:
            break
        start_at += max_results

    return comments


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: fetch_comments.py <ISSUE_KEY_OR_URL>", file=sys.stderr)
        raise SystemExit(2)

    issue_key = _extract_issue_key(sys.argv[1])
    base_url = _require_env("ATLASSIAN_URL").rstrip("/")
    auth_header = _load_auth()
    comments = fetch_comments(base_url, auth_header, issue_key)
    print(json.dumps(comments, indent=2))


if __name__ == "__main__":
    main()
