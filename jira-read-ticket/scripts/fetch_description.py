#!/usr/bin/env python3
"""
Fetch description details for a Jira ticket.

Outputs JSON containing description, optional acceptance criteria, labels, parent,
status, created_at, and updated_at fields.

Usage:
  python fetch_description.py ABC-123 > description.json
  python fetch_description.py https://example.atlassian.net/browse/ABC-123 > description.json
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


def _find_acceptance_criteria_field_id(base_url: str, auth_header: str) -> str | None:
    fields = _request_json("GET", f"{base_url}/rest/api/3/field", auth_header)
    if not isinstance(fields, list):
        return None

    for field in fields:
        name = (field.get("name") or "").strip().lower()
        if name == "acceptance criteria":
            return field.get("id")

    for field in fields:
        name = (field.get("name") or "").strip().lower()
        if "acceptance criteria" in name:
            return field.get("id")

    return None


def fetch_description(base_url: str, auth_header: str, issue_key: str) -> dict[str, Any]:
    acceptance_field_id = _find_acceptance_criteria_field_id(base_url, auth_header)
    fields = ["description", "labels", "parent", "status", "created", "updated"]
    if acceptance_field_id:
        fields.append(acceptance_field_id)

    query = urllib.parse.urlencode({"fields": ",".join(fields)})
    encoded_key = urllib.parse.quote(issue_key)
    url = f"{base_url}/rest/api/3/issue/{encoded_key}?{query}"
    data = _request_json("GET", url, auth_header)

    issue_fields = data.get("fields") or {}
    parent = issue_fields.get("parent") or {}
    parent_fields = parent.get("fields") or {}
    parent_key = parent.get("key")
    parent_value = None
    if parent_key or parent_fields:
        parent_value = {
            "key": parent_key,
            "title": parent_fields.get("summary"),
            "url": f"{base_url}/browse/{parent_key}" if parent_key else None,
        }

    result = {
        "key": data.get("key"),
        "url": f"{base_url}/browse/{issue_key}",
        "description_markdown": render_markdown(issue_fields.get("description")),
        "acceptance_criteria_markdown": render_markdown(
            issue_fields.get(acceptance_field_id) if acceptance_field_id else None
        ),
        "labels": issue_fields.get("labels") or [],
        "parent": parent_value,
        "status": (issue_fields.get("status") or {}).get("name"),
        "created_at": issue_fields.get("created"),
        "updated_at": issue_fields.get("updated"),
    }
    return result


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: fetch_description.py <ISSUE_KEY_OR_URL>", file=sys.stderr)
        raise SystemExit(2)

    issue_key = _extract_issue_key(sys.argv[1])
    base_url = _require_env("ATLASSIAN_URL").rstrip("/")
    auth_header = _load_auth()
    result = fetch_description(base_url, auth_header, issue_key)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
