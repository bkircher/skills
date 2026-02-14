#!/usr/bin/env python3
"""
Fetch a Confluence page by ID or URL.

Usage:
  python fetch_page.py 123456
  python fetch_page.py 123456 --children
  python fetch_page.py "https://example.atlassian.net/wiki/spaces/DEV/pages/123456/Title"
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
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

PAGE_ID_FROM_URL = re.compile(r"/wiki/spaces/[^/]+/pages/(\d+)")
PAGE_ID_QUERY = re.compile(r"pageId=(\d+)")


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


def _extract_page_id(value: str) -> str:
    if value.isdigit():
        return value
    match = PAGE_ID_FROM_URL.search(value)
    if match:
        return match.group(1)
    match = PAGE_ID_QUERY.search(value)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract page ID from: {value}")


def _fetch_children(
    base_url: str, auth_header: str, page_id: str
) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    cursor_url: str | None = (
        f"{base_url}/wiki/api/v2/pages/{page_id}/children?limit=100"
    )

    while cursor_url:
        data = _request_json("GET", cursor_url, auth_header)
        for child in data.get("results") or []:
            webui = (child.get("_links") or {}).get("webui") or ""
            child_url = base_url + "/wiki" + webui if webui else ""
            children.append(
                {
                    "id": child.get("id"),
                    "title": child.get("title"),
                    "url": child_url,
                }
            )
        next_link = (data.get("_links") or {}).get("next")
        if next_link:
            if next_link.startswith("http"):
                cursor_url = next_link
            else:
                cursor_url = base_url + next_link
        else:
            cursor_url = None

    return children


def fetch_page(
    base_url: str, auth_header: str, page_id: str, include_children: bool
) -> dict[str, Any]:
    url = (
        f"{base_url}/wiki/api/v2/pages/{page_id}"
        f"?body-format=atlas_doc_format&include-labels=true"
    )
    page = _request_json("GET", url, auth_header)

    body_adf_raw = (page.get("body") or {}).get("atlas_doc_format", {}).get("value")
    body_md = ""
    if body_adf_raw:
        try:
            adf = json.loads(body_adf_raw)
            body_md = render_markdown(adf)
        except (json.JSONDecodeError, TypeError):
            pass

    webui = (page.get("_links") or {}).get("webui") or ""
    page_url = base_url + "/wiki" + webui if webui else ""

    labels = [
        label.get("name")
        for label in (page.get("labels") or {}).get("results") or []
        if label.get("name")
    ]

    version = (page.get("version") or {}).get("number")

    result: dict[str, Any] = {
        "id": page.get("id"),
        "title": page.get("title"),
        "space_id": page.get("spaceId"),
        "url": page_url,
        "body_markdown": body_md,
        "labels": labels,
        "version": version,
        "created_at": page.get("createdAt"),
        "updated_at": (page.get("version") or {}).get("createdAt"),
    }

    if include_children:
        result["children"] = _fetch_children(base_url, auth_header, page_id)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch a Confluence page.")
    parser.add_argument("page", help="Page ID or URL")
    parser.add_argument(
        "--children", action="store_true", help="Include child pages"
    )
    args = parser.parse_args()

    page_id = _extract_page_id(args.page)
    base_url = _require_env("ATLASSIAN_URL").rstrip("/")
    auth_header = _load_auth()
    result = fetch_page(base_url, auth_header, page_id, args.children)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
