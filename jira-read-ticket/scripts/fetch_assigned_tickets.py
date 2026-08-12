#!/usr/bin/env python3
"""
Fetch all Jira tickets assigned to the current user.

Outputs JSON containing each ticket's key, title, URL, status, priority, and labels.

Usage:
  python fetch_assigned_tickets.py | jq
"""

import base64
import json
import os
import sys
import urllib.error
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
    max_results: int,
    next_page_token: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "jql": jql,
        "fields": fields,
        "maxResults": max_results,
    }
    if next_page_token is not None:
        payload["nextPageToken"] = next_page_token

    url = f"{base_url}/rest/api/3/search/jql"
    return _request_json("POST", url, auth_header, payload=payload)


def fetch_assigned_tickets(base_url: str, auth_header: str) -> list[dict[str, Any]]:
    jql = "assignee = currentUser() order by updated DESC"
    fields = ["summary", "status", "priority", "labels", "created", "updated"]
    max_results = 100
    next_page_token: str | None = None
    tickets: list[dict[str, Any]] = []

    while True:
        data = _search_page(
            base_url=base_url,
            auth_header=auth_header,
            jql=jql,
            fields=fields,
            max_results=max_results,
            next_page_token=next_page_token,
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

        if data.get("isLast") is True:
            break

        next_page_token = data.get("nextPageToken")
        if not isinstance(next_page_token, str) or not next_page_token:
            raise RuntimeError(
                "Jira search response is not the last page and has no nextPageToken"
            )

    tickets.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return tickets


def main() -> None:
    base_url = _require_env("ATLASSIAN_URL").rstrip("/")
    auth_header = _load_auth()
    tickets = fetch_assigned_tickets(base_url, auth_header)
    print(json.dumps(tickets, indent=2))


if __name__ == "__main__":
    main()
