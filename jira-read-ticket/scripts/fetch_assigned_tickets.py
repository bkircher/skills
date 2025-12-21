#!/usr/bin/env python3
"""
Fetch all Jira tickets assigned to the current user.

Outputs JSON containing each ticket's key, title, URL, status, priority, and labels.

Usage:
  python fetch_assigned_tickets.py | jq
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


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


def _request_json(
    method: str,
    url: str,
    auth_header: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None
    headers = {
        "Accept": "application/json",
        "Authorization": auth_header,
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RequestError(e.code, url, err_body) from e

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse JSON from {url}: {e}\nRaw:\n{raw}") from e


class RequestError(RuntimeError):
    def __init__(self, status: int, url: str, body: str) -> None:
        super().__init__(f"HTTP {status} for {url}\n{body}")
        self.status = status
        self.url = url
        self.body = body


def _search_page(
    base_url: str,
    auth_header: str,
    jql: str,
    fields: list[str],
    start_at: int,
    max_results: int,
    mode: str,
) -> dict[str, Any]:
    url = f"{base_url}/rest/api/3/search/jql"
    if mode == "post-object":
        payload = {
            "jql": {"query": jql},
            "fields": fields,
            "startAt": start_at,
            "maxResults": max_results,
        }
        return _request_json("POST", url, auth_header, payload=payload)
    if mode == "post-string":
        payload = {
            "jql": jql,
            "fields": fields,
            "startAt": start_at,
            "maxResults": max_results,
        }
        return _request_json("POST", url, auth_header, payload=payload)
    if mode == "get":
        query = {
            "jql": jql,
            "fields": ",".join(fields),
            "startAt": str(start_at),
            "maxResults": str(max_results),
        }
        return _request_json(
            "GET",
            f"{url}?{urllib.parse.urlencode(query)}",
            auth_header,
        )
    raise ValueError(f"Unknown search mode: {mode}")


def _search_page_with_fallback(
    base_url: str,
    auth_header: str,
    jql: str,
    fields: list[str],
    start_at: int,
    max_results: int,
) -> tuple[dict[str, Any], str]:
    last_error: RequestError | None = None
    for mode in ("post-object", "post-string", "get"):
        try:
            return _search_page(
                base_url=base_url,
                auth_header=auth_header,
                jql=jql,
                fields=fields,
                start_at=start_at,
                max_results=max_results,
                mode=mode,
            ), mode
        except RequestError as e:
            last_error = e
            if e.status not in (400, 405):
                raise
    assert last_error is not None
    raise last_error


def fetch_assigned_tickets(base_url: str, auth_header: str) -> list[dict[str, Any]]:
    jql = "assignee = currentUser() order by updated DESC"
    fields = ["summary", "status", "priority", "labels", "created", "updated"]
    start_at = 0
    max_results = 100
    tickets: list[dict[str, Any]] = []
    request_mode: str | None = None

    while True:
        if request_mode is None:
            data, request_mode = _search_page_with_fallback(
                base_url=base_url,
                auth_header=auth_header,
                jql=jql,
                fields=fields,
                start_at=start_at,
                max_results=max_results,
            )
        else:
            data = _search_page(
                base_url=base_url,
                auth_header=auth_header,
                jql=jql,
                fields=fields,
                start_at=start_at,
                max_results=max_results,
                mode=request_mode,
            )

        issues = data.get("issues") or []
        for issue in issues:
            issue_fields = issue.get("fields") or {}
            key = issue.get("key")
            status_name = (issue_fields.get("status") or {}).get("name")
            if status_name in {"Done", "Cancelled", "Closed"}:
                continue
            tickets.append(
                {
                    "key": key,
                    "title": issue_fields.get("summary"),
                    "url": f"{base_url}/browse/{key}" if key else None,
                    "status": status_name,
                    "priority": (issue_fields.get("priority") or {}).get("name"),
                    "labels": issue_fields.get("labels") or [],
                    "created_at": issue_fields.get("created"),
                    "updated_at": issue_fields.get("updated"),
                }
            )

        total = data.get("total")
        start_at = data.get("startAt", start_at)
        max_results = data.get("maxResults", max_results)

        if total is None or start_at + max_results >= total:
            break
        start_at += max_results

    tickets.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return tickets


def main() -> None:
    base_url = _require_env("ATLASSIAN_URL").rstrip("/")
    auth_header = _load_auth()
    tickets = fetch_assigned_tickets(base_url, auth_header)
    print(json.dumps(tickets, indent=2))


if __name__ == "__main__":
    main()
