"""Jira metadata, cached only within one client-bound operation context."""

import copy
import re
import urllib.parse
from typing import Any

from client import JiraClient


class Metadata:
    def __init__(self, client: JiraClient) -> None:
        self.client = client
        # A Metadata instance belongs to one site and authenticated client.
        # Do not persist permissions or field contexts between CLI invocations.
        self._cache: dict[tuple[str, ...], Any] = {}

    def fields(self) -> list[dict[str, Any]]:
        key = ("fields",)
        if key not in self._cache:
            fields = self.client.request_array("GET", "/rest/api/3/field")
            if any(not isinstance(field, dict) or not isinstance(field.get("id"), str)
                   for field in fields):
                raise RuntimeError("Jira returned invalid field metadata")
            self._cache[key] = fields
        return copy.deepcopy(self._cache[key])

    def acceptance_fields(self) -> list[str]:
        # Exact names only. Multiple matches remain separate; do not guess.
        return [field["id"] for field in self.fields()
                if field.get("name", "").strip().casefold() == "acceptance criteria"]

    def issue_types(self, project: str) -> list[dict[str, Any]]:
        project = project_identifier(project)
        key = ("types", project)
        if key not in self._cache:
            path = f"/rest/api/3/issue/createmeta/{project}/issuetypes"
            self._cache[key] = self._pages(path, "issueTypes")
        return copy.deepcopy(self._cache[key])

    def for_create(self, project: str, issue_type: str) -> dict[str, Any]:
        project = project_identifier(project)
        if not isinstance(issue_type, str) or not issue_type.strip():
            raise ValueError("An issue type name or ID is required")
        if issue_type.isascii() and issue_type.isdecimal():
            type_id = issue_type
        else:
            matches = [item for item in self.issue_types(project)
                       if item.get("name", "").casefold() == issue_type.casefold()]
            if len(matches) != 1:
                raise ValueError("Issue type is missing or ambiguous; use metadata --project")
            type_id = str(matches[0]["id"])
            if not type_id.isascii() or not type_id.isdecimal():
                raise RuntimeError("Jira returned an invalid issue type ID")
        key = ("create", project, type_id)
        if key not in self._cache:
            path = f"/rest/api/3/issue/createmeta/{project}/issuetypes/{type_id}"
            items = self._pages(path, "fields")
            fields: dict[str, Any] = {}
            for field in items:
                field_id = field.get("fieldId")
                if not isinstance(field_id, str) or field_id in fields:
                    raise RuntimeError("Jira returned missing or duplicate create field IDs")
                fields[field_id] = field
            self._cache[key] = {"project": project, "issue_type_id": type_id, "fields": fields}
        return copy.deepcopy(self._cache[key])

    def for_edit(self, issue_key: str) -> dict[str, Any]:
        # Callers supply a validated key. Each issue can have a different context.
        key = ("edit", issue_key)
        if key not in self._cache:
            path = f"/rest/api/3/issue/{urllib.parse.quote(issue_key, safe='')}/editmeta"
            data = self.client.request_object("GET", path)
            self._cache[key] = edit_fields(data)
        return copy.deepcopy(self._cache[key])

    def _pages(self, path: str, collection: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        start = 0
        while True:
            data = self.client.request_object("GET", f"{path}?startAt={start}&maxResults=100")
            page = data.get(collection)
            total = data.get("total")
            if (not isinstance(page, list) or any(not isinstance(item, dict) for item in page)
                    or type(total) is not int or total < 0 or data.get("startAt") != start):
                raise RuntimeError("Jira returned invalid metadata pagination")
            items.extend(page)
            start += len(page)
            if start >= total:
                return items
            if not page:
                raise RuntimeError("Jira metadata pagination made no progress")


def edit_fields(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("fields"), dict):
        raise RuntimeError("Jira did not return edit metadata; no write was sent")
    if any(not isinstance(value, dict) for value in data["fields"].values()):
        raise RuntimeError("Jira returned invalid edit metadata; no write was sent")
    return data["fields"]


def project_identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*|[0-9]+", value):
        raise ValueError("Supply one project key or numeric project ID")
    return value.upper()
