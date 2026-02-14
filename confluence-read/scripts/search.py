#!/usr/bin/env python3
"""
Search Confluence pages via CQL.

Usage:
  python search.py "deployment guide" --space DEV --limit 5
  python search.py "onboarding"
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_JIRA_SCRIPTS = os.path.join(
    os.path.dirname(__file__), "..", "..", "jira-read-ticket", "scripts"
)
sys.path.insert(0, _JIRA_SCRIPTS)
from jira import render_markdown  # noqa: E402


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


def _build_cql(query: str, space: str | None) -> str:
    clauses = ['type = "page"', f'text ~ "{query}"']
    if space:
        clauses.append(f'space = "{space}"')
    return " AND ".join(clauses)


def search(
    base_url: str, auth_header: str, query: str, space: str | None, limit: int
) -> list[dict[str, Any]]:
    cql = _build_cql(query, space)
    results: list[dict[str, Any]] = []
    cursor_url: str | None = (
        f"{base_url}/wiki/rest/api/search"
        f"?cql={urllib.parse.quote(cql)}"
        f"&expand=content.body.atlas_doc_format"
        f"&limit={min(limit, 25)}"
    )

    while cursor_url and len(results) < limit:
        data = _request_json("GET", cursor_url, auth_header)
        links_base = (data.get("_links") or {}).get("base") or base_url

        for item in data.get("results") or []:
            if len(results) >= limit:
                break
            content = item.get("content") or {}
            body_adf_raw = (
                (content.get("body") or {})
                .get("atlas_doc_format", {})
                .get("value")
            )
            body_md = ""
            if body_adf_raw:
                try:
                    adf = json.loads(body_adf_raw)
                    body_md = render_markdown(adf)
                except (json.JSONDecodeError, TypeError):
                    pass

            webui = (content.get("_links") or {}).get("webui") or ""
            page_url = links_base + webui if webui else ""

            space_obj = content.get("space") or content.get("_expandable") or {}
            space_key = space_obj.get("key") or ""

            results.append(
                {
                    "id": content.get("id"),
                    "title": content.get("title") or item.get("title"),
                    "space_key": space_key,
                    "url": page_url,
                    "excerpt": item.get("excerpt") or "",
                    "last_modified": item.get("lastModified")
                    or content.get("history", {}).get("lastUpdated", {}).get("when"),
                    "body_markdown": body_md,
                }
            )

        next_link = (data.get("_links") or {}).get("next")
        if next_link:
            cursor_url = links_base + next_link
        else:
            cursor_url = None

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Search Confluence pages.")
    parser.add_argument("query", help="Search query text")
    parser.add_argument("--space", default=None, help="Confluence space key filter")
    parser.add_argument("--limit", type=int, default=10, help="Max results (default 10)")
    args = parser.parse_args()

    base_url = _require_env("ATLASSIAN_URL").rstrip("/")
    auth_header = _load_auth()
    results = search(base_url, auth_header, args.query, args.space, args.limit)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
