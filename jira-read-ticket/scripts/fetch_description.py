#!/usr/bin/env python3
"""
Fetch description details for a Jira ticket.

Outputs JSON containing description, optional acceptance criteria, labels, parent,
status, created_at, and updated_at fields.

Usage:
  python fetch_description.py ABC-123 > description.json
  python fetch_description.py https://example.atlassian.net/browse/ABC-123 > description.json
"""

import json
import sys
import urllib.parse
from typing import Any

from adf import render_markdown
from jira import JiraClient, extract_issue_key


def _find_acceptance_criteria_field_id(client: JiraClient) -> str | None:
    fields = client.request_array("GET", "/rest/api/3/field")

    for field in fields:
        if not isinstance(field, dict):
            continue
        name = (field.get("name") or "").strip().lower()
        field_id = field.get("id")
        if name == "acceptance criteria" and isinstance(field_id, str):
            return field_id

    for field in fields:
        if not isinstance(field, dict):
            continue
        name = (field.get("name") or "").strip().lower()
        field_id = field.get("id")
        if "acceptance criteria" in name and isinstance(field_id, str):
            return field_id

    return None


def fetch_description(client: JiraClient, issue_key: str) -> dict[str, Any]:
    acceptance_field_id = _find_acceptance_criteria_field_id(client)
    fields = ["description", "labels", "parent", "status", "created", "updated"]
    if acceptance_field_id:
        fields.append(acceptance_field_id)

    query = urllib.parse.urlencode({"fields": ",".join(fields)})
    encoded_key = urllib.parse.quote(issue_key)
    path = f"/rest/api/3/issue/{encoded_key}?{query}"
    data = client.request_object("GET", path)

    issue_fields = data.get("fields") or {}
    parent = issue_fields.get("parent") or {}
    parent_fields = parent.get("fields") or {}
    parent_key = parent.get("key")
    parent_value = None
    if parent_key or parent_fields:
        parent_value = {
            "key": parent_key,
            "title": parent_fields.get("summary"),
            "url": f"{client.base_url}/browse/{parent_key}" if parent_key else None,
        }

    result = {
        "key": data.get("key"),
        "url": f"{client.base_url}/browse/{issue_key}",
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

    issue_key = extract_issue_key(sys.argv[1])
    client = JiraClient.from_env()
    result = fetch_description(client, issue_key)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
