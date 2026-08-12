#!/usr/bin/env python3
"""
Fetch all comments from a Jira ticket.

Usage:
  python fetch_comments.py ABC-123 | jq
  python fetch_comments.py https://example.atlassian.net/browse/ABC-123 | jq
"""

import json
import sys
import urllib.parse
from typing import Any

from adf import render_markdown
from jira import JiraClient, extract_issue_key


def fetch_comments(client: JiraClient, issue_key: str) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    start_at = 0
    max_results = 100
    encoded_key = urllib.parse.quote(issue_key)

    while True:
        path = (
            f"/rest/api/3/issue/{encoded_key}/comment"
            f"?startAt={start_at}&maxResults={max_results}"
        )
        data = client.request_object("GET", path)
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

    issue_key = extract_issue_key(sys.argv[1])
    client = JiraClient.from_env()
    comments = fetch_comments(client, issue_key)
    print(json.dumps(comments, indent=2))


if __name__ == "__main__":
    main()
