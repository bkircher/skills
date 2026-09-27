"""Single-issue Jira operations through the shared REST v3 client."""

import difflib
import hashlib
import json
import urllib.parse
from typing import Any

from adf import render_markdown
from changes import (
    FIELD_ID, build_changes, validate_fields, validate_label_operations,
    validate_spec, validate_transition_fields, validate_transition_spec, value_matches,
)
from client import JiraClient, RequestError, extract_issue_key
from metadata import Metadata, edit_fields, project_identifier
from rich_text import read_sections


DEFAULT_FIELDS = [
    "summary", "description", "labels", "status", "issuetype", "project",
    "priority", "assignee", "reporter", "parent", "created", "updated",
]
SEARCH_FIELDS = ["summary", "status", "assignee", "priority", "labels", "updated"]
REJECTED_STATUSES = {400, 401, 403, 404, 409, 422, 429}


class JiraIssues:
    def __init__(self, client: JiraClient) -> None:
        self.client = client
        self.metadata = Metadata(client)

    def search(
        self, *, jql: str | None = None, text: str | None = None,
        project: str | None = None, assignee: str | None = None,
        open_only: bool = False, limit: int = 20,
        fields: list[str] | None = None, page_token: str | None = None,
    ) -> dict[str, Any]:
        _limit(limit)
        selected = _field_list(fields if fields is not None else SEARCH_FIELDS)
        if jql is not None and any((text is not None, project is not None, assignee is not None, open_only)):
            raise ValueError("Use either --jql or search filters, not both")
        if jql is None:
            clauses = []
            if text:
                clauses.append("text ~ " + json.dumps(text, ensure_ascii=False))
            if project:
                clauses.append("project = " + json.dumps(project_identifier(project)))
            if assignee:
                value = "currentUser()" if assignee == "me" else json.dumps(assignee)
                clauses.append("assignee = " + value)
            if open_only:
                clauses.append('statusCategory != "Done"')
            if not clauses:
                raise ValueError("Supply search text, a filter, or explicit JQL")
            jql = " AND ".join(clauses) + " ORDER BY updated DESC"
        if not jql.strip():
            raise ValueError("JQL must not be empty")
        issues = []
        token = page_token
        seen = {token} if token else set()
        while len(issues) < limit:
            page_size = min(100, limit - len(issues))
            payload: dict[str, Any] = {"jql": jql, "fields": selected, "maxResults": page_size}
            if token:
                payload["nextPageToken"] = token
            data = self.client.request_object("POST", "/rest/api/3/search/jql", payload)
            page = data.get("issues")
            if not isinstance(page, list) or len(page) > page_size:
                raise RuntimeError("Jira returned an invalid search page")
            issues.extend(self._format_issue(item) for item in page)
            if data.get("isLast") is True:
                token = None
                break
            token = data.get("nextPageToken")
            if not isinstance(token, str) or not token or token in seen or not page:
                raise RuntimeError("Jira search pagination made no progress")
            seen.add(token)
        return {"jql": jql, "issues": issues, "count": len(issues),
                "truncated": token is not None, "next_page_token": token}

    def get(
        self, issue: str, *, fields: list[str] | None = None,
        comments: bool = False, comment_limit: int = 20, comment_start: int = 0,
        acceptance_criteria: bool = False, acceptance_field: str | None = None,
        for_update: bool = False, raw_adf: bool = False,
    ) -> dict[str, Any]:
        key = self.issue_key(issue)
        selected = _field_list(fields if fields is not None else DEFAULT_FIELDS)
        custom = []
        if acceptance_field:
            custom = _field_list([acceptance_field])
        elif acceptance_criteria:
            custom = self.metadata.acceptance_fields()
        if acceptance_criteria or acceptance_field:
            selected = list(dict.fromkeys([*selected, "description", *custom]))
        data = self._fetch(key, selected)
        raw = data["fields"]
        result = self._format_issue(data, raw_adf=raw_adf)
        result["missing_fields"] = sorted(set(selected) - raw.keys())
        if "description" in raw or custom:
            sources = [{"field": "description", "heading": section["heading"],
                        "markdown": render_markdown(section["document"])}
                       for section in read_sections(raw.get("description"), "Acceptance criteria")]
            sources.extend({"field": field, "markdown": render_markdown(raw[field])}
                           for field in custom if field in raw)
            result["acceptance_criteria"] = {
                "sources": sources,
                "custom_fields_checked": bool(acceptance_criteria or acceptance_field),
                "missing_custom_fields": sorted(set(custom) - raw.keys()),
            }
        if for_update:
            result["snapshot"] = self._snapshot(data["key"], raw)
        if comments:
            result["comments"] = self.comments(data["key"], limit=comment_limit,
                                                start=comment_start, raw_adf=raw_adf)
        return result

    def comments(
        self, issue: str, *, limit: int = 20, start: int = 0, raw_adf: bool = False,
    ) -> dict[str, Any]:
        _limit(limit)
        if type(start) is not int or start < 0:
            raise ValueError("Comment start must be a non-negative integer")
        key = self.issue_key(issue)
        items = []
        position = start
        total = 0
        while len(items) < limit:
            size = min(100, limit - len(items))
            path = f"/rest/api/3/issue/{key}/comment?startAt={position}&maxResults={size}"
            data = self.client.request_object("GET", path)
            page = data.get("comments")
            total = data.get("total")
            if (not isinstance(page, list) or type(total) is not int or total < 0
                    or data.get("startAt") != position or len(page) > size):
                raise RuntimeError("Jira returned invalid comment pagination")
            for comment in page:
                if not isinstance(comment, dict):
                    raise RuntimeError("Jira returned invalid comment data")
                item = {name: comment.get(name) for name in ("id", "author", "created", "updated")}
                item["body_markdown"] = render_markdown(comment.get("body"))
                if raw_adf:
                    item["body_adf"] = comment.get("body")
                items.append(item)
            position += len(page)
            if position >= total:
                break
            if not page:
                raise RuntimeError("Jira comment pagination made no progress")
        return {"items": items, "total": total, "start_at": start,
                "truncated": position < total,
                "next_start_at": position if position < total else None}

    def transitions(self, issue: str) -> dict[str, Any]:
        key = self.issue_key(issue)
        data = self._fetch(key, ["status"])
        key = extract_issue_key(data["key"])
        status = _status(data["fields"].get("status"))
        choices = self._transitions(key)
        return {"key": key, "url": f"{self.client.base_url}/browse/{key}",
                "current_status": status, "transitions": choices,
                "snapshot": self._snapshot(key, {"status": data["fields"]["status"]})}

    def transition(
        self, issue: str, spec: dict[str, Any] | None = None, *,
        transition_id: str | None = None, name: str | None = None,
        to_status: str | None = None, preview: bool = False,
    ) -> dict[str, Any]:
        key = self.issue_key(issue)
        selectors = {"id": transition_id, "name": name, "to-status": to_status}
        if sum(value is not None for value in selectors.values()) != 1:
            raise ValueError("Supply exactly one of --id, --name, or --to-status")
        for selector, value in selectors.items():
            if value is not None and (not isinstance(value, str) or not value.strip()
                                      or (selector == "id" and (not value.isascii() or not value.isdecimal()))):
                raise ValueError(f"Invalid transition {selector}")
        if spec is None:
            if not preview:
                raise ValueError("Apply requires --input with expected from a preview")
            spec = {}
        affected = validate_transition_spec(spec)
        expected = spec.get("expected")
        covered = ["status", *affected]
        if expected is None and not preview:
            raise ValueError("Transition requires expected: copy the snapshot from --preview")
        if expected is not None:
            self._validate_snapshot(expected, key, covered)

        choices = self._transitions(key)
        selector, value = next((kind, item) for kind, item in selectors.items() if item is not None)
        matches = [choice for choice in choices if (
            choice["id"] if selector == "id" else
            choice["name"] if selector == "name" else choice["to"]["name"]
        ).casefold() == value.casefold()]
        if len(matches) != 1:
            # An old snapshot takes precedence over a missing workflow choice.
            if expected is not None:
                data = self._fetch(key, covered)
                if self._transition_conflict(data, key, covered, expected):
                    return {**self._result("conflict", "transition", key), "verified": False,
                            "message": "Source fields changed. Read the issue again. No write was sent."}
            raise ValueError("Transition is unavailable or ambiguous; list transitions again")
        choice = matches[0]
        metadata = choice["fields"]
        required = [field for field, info in metadata.items() if info["required"]]
        selected_fields = list(dict.fromkeys(["status", *affected, *required]))
        data = self._fetch(key, selected_fields)
        current = data["fields"]
        if self._transition_conflict(data, key, covered, expected):
            return {**self._result("conflict", "transition", key), "verified": False,
                    "message": "Source fields changed. Read the issue again. No write was sent."}
        if "status" not in current or set(affected) - current.keys():
            raise ValueError("Jira omitted a transition source field; no write was sent")
        before = _status(current["status"])
        result = {**self._result("preview", "transition", key),
                  "transition": {"id": choice["id"], "name": choice["name"], "to": choice["to"]},
                  "before_status": before, "target_status": choice["to"],
                  "screen_fields": metadata, "required_fields": sorted(required),
                  "changed_fields": affected}
        if before["id"] == choice["to"]["id"]:
            raise ValueError("Self-loop transitions are not supported; no write was sent")
        fields, _ = build_changes(spec, metadata, current)
        validate_transition_fields(fields, metadata, current)
        if preview:
            result["changes"] = {field: _diff(current[field], fields[field]) for field in affected}
            result["snapshot"] = self._snapshot(key, {field: current[field] for field in covered})
            return result
        payload = {"transition": {"id": choice["id"]}}
        if fields:
            payload["fields"] = fields
        try:
            self.client.request_json("POST", f"/rest/api/3/issue/{key}/transitions", payload)
        except (RuntimeError, OSError) as error:
            return self._write_error(result, error)
        try:
            saved = self._fetch(key, list(dict.fromkeys(["status", "resolution", *affected])))
        except (RuntimeError, OSError) as error:
            return {**result, "status": "unverified", "write_accepted": True,
                    "verified": False, "message": f"Write accepted, but verification failed: {error}"}
        actual = saved["fields"]
        result["observed_resolution"] = actual.get("resolution")
        try:
            saved_status = _status(actual.get("status"))
        except RuntimeError as error:
            return {**result, "status": "unverified", "write_accepted": True,
                    "verified": False, "message": f"Write accepted, but verification failed: {error}"}
        mismatches = [field for field, value in fields.items()
                      if field not in actual or not value_matches(
                          value, actual[field], field, schema=metadata[field].get("schema"))]
        if saved["key"] != key or saved_status["id"] != choice["to"]["id"]:
            mismatches.append("status")
        if "resolution" not in actual:
            mismatches.append("resolution")
        if mismatches:
            return {**result, "status": "unverified", "write_accepted": True,
                    "verified": False, "mismatched_fields": sorted(set(mismatches)),
                    "message": "Write accepted, but the saved issue differs. Do not repeat the write automatically."}
        return {**result, "status": "transitioned", "write_accepted": True, "verified": True}

    def _transitions(self, key: str) -> list[dict[str, Any]]:
        path = f"/rest/api/3/issue/{key}/transitions?expand=transitions.fields"
        data = self.client.request_object("GET", path)
        items = data.get("transitions")
        if not isinstance(items, list):
            raise RuntimeError("Jira returned invalid transition data")
        choices = []
        for item in items:
            if not isinstance(item, dict) or not _jira_id(item.get("id")) or not _name(item.get("name")):
                raise RuntimeError("Jira returned invalid transition IDs or names")
            target = _status(item.get("to"))
            metadata = item.get("fields")
            if not isinstance(metadata, dict):
                raise RuntimeError("Jira did not return transition-screen metadata; no write was sent")
            for field, info in metadata.items():
                if (not isinstance(field, str) or not FIELD_ID.fullmatch(field)
                        or not isinstance(info, dict) or type(info.get("required")) is not bool
                        or not isinstance(info.get("schema"), dict)
                        or not isinstance(info.get("operations"), list)
                        or any(not isinstance(op, str) for op in info["operations"])
                        or ("hasDefaultValue" in info and type(info["hasDefaultValue"]) is not bool)
                        or ("allowedValues" in info and not isinstance(info["allowedValues"], list))):
                    raise RuntimeError("Jira returned invalid transition-screen metadata")
            choices.append({"id": item["id"], "name": item["name"], "to": target,
                            "fields": metadata})
        return choices

    def _transition_conflict(
        self, data: dict[str, Any], key: str, covered: list[str], expected: Any,
    ) -> bool:
        return (data["key"] != key or (expected is not None and any(
            field not in data["fields"] or expected["hashes"][field] != _hash(data["fields"][field])
            for field in covered)))

    def update(self, issue: str, spec: dict[str, Any], *, preview: bool = False) -> dict[str, Any]:
        key = self.issue_key(issue)
        affected = validate_spec(spec, creating=False)
        expected = spec.get("expected")
        if expected is None and not preview:
            raise ValueError("Update requires expected: copy the snapshot from get --for-update or --preview")
        if expected is not None:
            self._validate_snapshot(expected, key, affected)
        data = self._fetch(key, affected, edit=True)
        current = data["fields"]
        if set(affected) - current.keys():
            raise ValueError("Jira omitted an affected field; no write was sent")
        result = self._result("preview", "update", key)
        if data["key"] != key or (expected is not None and any(
            expected["hashes"][field] != _hash(current[field]) for field in affected
        )):
            return {**result, "status": "conflict", "verified": False,
                    "message": "Source fields changed. Read the issue again. No write was sent."}
        editable = edit_fields(data.get("editmeta"))
        fields, operations = build_changes(spec, editable, current)
        validate_fields(fields, editable)
        validate_label_operations(operations, editable)
        fields = {field: value for field, value in fields.items()
                  if not value_matches(value, current[field], field,
                                       schema=editable[field].get("schema"))}
        changed = sorted(set(fields) | set(operations))
        result["changed_fields"] = changed
        if preview:
            after = {**fields}
            if operations:
                after["labels"] = _changed_labels(current.get("labels") or [], operations["labels"])
            result["changes"] = {field: _diff(current[field], after[field]) for field in changed}
            result["snapshot"] = self._snapshot(key, {field: current[field] for field in affected})
            return result
        if not changed:
            return {**result, "status": "unchanged", "verified": True}
        payload: dict[str, Any] = {}
        if fields:
            payload["fields"] = fields
        if operations:
            payload["update"] = operations
        try:
            self.client.request_json("PUT", f"/rest/api/3/issue/{key}", payload)
        except (RuntimeError, OSError) as error:
            return self._write_error(result, error)
        return self._verify(result, fields, operations, editable)

    def create(self, spec: dict[str, Any], *, preview: bool = False) -> dict[str, Any]:
        validate_spec(spec, creating=True)
        project = project_identifier(spec.get("project"))
        summary = spec.get("fields", {}).get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("Creation requires non-empty fields.summary")
        metadata = self.metadata.for_create(project, spec.get("issue_type"))
        fields, operations = build_changes(spec, metadata["fields"], {})
        fields["project"] = {"id" if project.isdecimal() else "key": project}
        fields["issuetype"] = {"id": metadata["issue_type_id"]}
        validate_fields(fields, metadata["fields"], creating=True)
        result: dict[str, Any] = {"status": "preview", "operation": "create",
                                  "changed_fields": sorted(fields)}
        if preview:
            result["fields"] = _readable_fields(fields)
            return result
        try:
            created = self.client.request_object("POST", "/rest/api/3/issue", {"fields": fields})
        except (RuntimeError, OSError) as error:
            return self._write_error(result, error)
        try:
            key = extract_issue_key(created.get("key", ""))
        except (ValueError, AttributeError):
            return {**result, "status": "unknown", "verified": False,
                    "message": "Jira accepted the request but returned no valid issue key. Do not create again."}
        result.update(self._result("preview", "create", key))
        return self._verify(result, fields, operations, metadata["fields"])

    def issue_key(self, value: str) -> str:
        key = extract_issue_key(value)
        if "://" in value:
            supplied = urllib.parse.urlsplit(value.strip())
            configured = urllib.parse.urlsplit(self.client.base_url)
            if (supplied.hostname, supplied.port or 443) != (configured.hostname, configured.port or 443):
                raise ValueError("The issue URL belongs to another site. Check ATLASSIAN_URL before continuing")
        return key

    def _fetch(self, key: str, fields: list[str], *, edit: bool = False) -> dict[str, Any]:
        query = {"fields": ",".join(fields)}
        if edit:
            query["expand"] = "editmeta"
        data = self.client.request_object("GET", f"/rest/api/3/issue/{key}?{urllib.parse.urlencode(query)}")
        if not isinstance(data.get("fields"), dict) or not isinstance(data.get("key"), str):
            raise RuntimeError("Jira returned invalid issue data")
        return data

    def _format_issue(self, data: Any, *, raw_adf: bool = False) -> dict[str, Any]:
        if (not isinstance(data, dict) or not isinstance(data.get("fields"), dict)
                or not isinstance(data.get("key"), str)):
            raise RuntimeError("Jira returned invalid issue data")
        key = extract_issue_key(data["key"])
        raw = data["fields"]
        rich = {field: value for field, value in raw.items()
                if isinstance(value, dict) and value.get("type") == "doc"}
        result = {"key": key, "url": f"{self.client.base_url}/browse/{key}",
                  "fields": _readable_fields(raw), "rich_text_fields": sorted(rich)}
        if raw_adf:
            result["raw_adf"] = rich
        return result

    def _snapshot(self, key: str, fields: dict[str, Any]) -> dict[str, Any]:
        return {"site": self.client.base_url, "issue": key,
                "hashes": {field: _hash(value) for field, value in fields.items()}}

    def _validate_snapshot(self, snapshot: Any, key: str, affected: list[str]) -> None:
        if (not isinstance(snapshot, dict) or snapshot.get("site") != self.client.base_url
                or snapshot.get("issue") != key or not isinstance(snapshot.get("hashes"), dict)):
            raise ValueError("expected must be a snapshot for this site and issue")
        if any(not isinstance(snapshot["hashes"].get(field), str) for field in affected):
            raise ValueError("The snapshot must include every affected field")

    def _result(self, status: str, operation: str, key: str) -> dict[str, Any]:
        return {"status": status, "operation": operation, "key": key,
                "url": f"{self.client.base_url}/browse/{key}"}

    def _write_error(self, result: dict[str, Any], error: Exception) -> dict[str, Any]:
        rejected = isinstance(error, RequestError) and error.status in REJECTED_STATUSES
        guidance = "No write was accepted." if rejected else (
            "The outcome is unknown. Do not repeat the write. Check Jira before another write."
        )
        return {**result, "status": "rejected" if rejected else "unknown",
                "verified": False, "message": f"{error}\n{guidance}"}

    def _verify(
        self, result: dict[str, Any], fields: dict[str, Any], operations: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        affected = sorted(set(fields) | set(operations))
        try:
            data = self._fetch(result["key"], affected)
        except (RuntimeError, OSError) as error:
            return {**result, "status": "unverified", "write_accepted": True,
                    "verified": False, "message": f"Write accepted, but verification failed: {error}"}
        actual = data["fields"]
        mismatches = [field for field, value in fields.items()
                      if field not in actual or not value_matches(
                          value, actual[field], field, schema=metadata.get(field, {}).get("schema"))]
        if operations:
            labels = actual.get("labels")
            if not isinstance(labels, list) or any(
                ("add" in change and change["add"] not in labels)
                or ("remove" in change and change["remove"] in labels)
                for change in operations["labels"]
            ):
                mismatches.append("labels")
        if mismatches or data["key"] != result["key"]:
            return {**result, "status": "unverified", "write_accepted": True,
                    "verified": False, "mismatched_fields": sorted(set(mismatches)),
                    "message": "Write accepted, but the saved issue differs. Do not repeat the write automatically."}
        return {**result, "status": "created" if result["operation"] == "create" else "updated",
                "write_accepted": True, "verified": True}


def _jira_id(value: Any) -> bool:
    return isinstance(value, str) and value.isascii() and value.isdecimal()


def _name(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _status(value: Any) -> dict[str, str]:
    if (not isinstance(value, dict) or not _jira_id(value.get("id"))
            or not _name(value.get("name"))):
        raise RuntimeError("Jira returned invalid status data")
    return {"id": value["id"], "name": value["name"]}


def _field_list(fields: list[str]) -> list[str]:
    if not fields or any(not isinstance(field, str) or not FIELD_ID.fullmatch(field) for field in fields):
        raise ValueError("Supply explicit field IDs, not wildcards or an empty field list")
    if "comment" in fields:
        raise ValueError("Use --comments for complete, paginated comment results")
    return list(dict.fromkeys(fields))


def _limit(limit: int) -> None:
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("Limit must be between 1 and 1000; use the returned cursor for more results")


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _readable_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {field: render_markdown(value) if isinstance(value, dict) and value.get("type") == "doc" else value
            for field, value in fields.items()}


def _changed_labels(current: list[str], operations: list[dict[str, str]]) -> list[str]:
    labels = list(current)
    for change in operations:
        if "add" in change:
            labels.append(change["add"])
        else:
            labels.remove(change["remove"])
    return labels


def _diff(before: Any, after: Any) -> dict[str, Any]:
    left = render_markdown(before) if isinstance(before, dict) and before.get("type") == "doc" else before
    right = render_markdown(after) if isinstance(after, dict) and after.get("type") == "doc" else after
    if isinstance(left, str) and isinstance(right, str):
        return {"diff": "\n".join(difflib.unified_diff(left.splitlines(), right.splitlines(),
                                                     fromfile="before", tofile="after", lineterm="")),
                "structural_change": left == right and before != after}
    return {"before": left, "after": right}
