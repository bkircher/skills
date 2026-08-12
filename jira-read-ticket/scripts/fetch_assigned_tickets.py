#!/usr/bin/env python3
"""
Fetch all Jira tickets assigned to the current user.

Outputs JSON containing each ticket's key, title, URL, status, priority, and labels.

Usage:
  python fetch_assigned_tickets.py | jq
"""

import json
from typing import Any

from jira import JiraClient


def _search_page(
    client: JiraClient,
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

    return client.request_object(
        method="POST",
        path="/rest/api/3/search/jql",
        payload=payload,
    )


def fetch_assigned_tickets(client: JiraClient) -> list[dict[str, Any]]:
    jql = "assignee = currentUser() order by updated DESC"
    fields = ["summary", "status", "priority", "labels", "created", "updated"]
    max_results = 100
    next_page_token: str | None = None
    tickets: list[dict[str, Any]] = []

    while True:
        data = _search_page(
            client=client,
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
                    "url": f"{client.base_url}/browse/{key}" if key else None,
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
    client = JiraClient.from_env()
    tickets = fetch_assigned_tickets(client)
    print(json.dumps(tickets, indent=2))


if __name__ == "__main__":
    main()
