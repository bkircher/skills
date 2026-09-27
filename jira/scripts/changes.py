"""Validate single-issue changes and build one Jira write payload."""

import copy
import math
import re
from typing import Any

from rich_text import from_markdown, from_text, replace_section, validate_document


PROTECTED = {
    "id", "key", "project", "issuetype", "status", "resolution", "created", "updated",
    "comment", "worklog", "attachment", "issuelinks", "subtasks", "watches", "votes",
}
FIELD_ID = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
REFERENCE_TYPES = {
    "user", "priority", "option", "project", "issuetype", "issuelink",
    "component", "version", "securitylevel", "group",
}
REFERENCE_FIELDS = {"assignee", "reporter", "priority", "project", "issuetype", "parent", "security", "resolution"}


def validate_spec(spec: Any, *, creating: bool) -> list[str]:
    if not isinstance(spec, dict):
        raise ValueError("Input must be one JSON object, not a list of issues")
    allowed = {"fields", "text", "sections"}
    allowed |= {"project", "issue_type"} if creating else {"expected", "labels"}
    if spec.keys() - allowed:
        raise ValueError("Unknown input keys: " + ", ".join(sorted(spec.keys() - allowed)))
    fields = spec.get("fields", {})
    text = spec.get("text", {})
    sections = spec.get("sections", [])
    if not isinstance(fields, dict) or not isinstance(text, dict) or not isinstance(sections, list):
        raise ValueError("fields and text must be objects; sections must be an array")
    overlap = fields.keys() & text.keys()
    if overlap:
        raise ValueError("Do not supply a field through both fields and text")
    affected = set(fields) | set(text)
    seen_sections: set[tuple[str, str]] = set()
    for section in sections:
        if not isinstance(section, dict) or section.keys() - {"field", "heading", "content", "create", "level"}:
            raise ValueError("Invalid section change")
        field = section.get("field", "description")
        heading = section.get("heading")
        if not isinstance(field, str) or not isinstance(heading, str) or not heading.strip():
            raise ValueError("Each section needs a field ID and a heading")
        if field in fields or field in text:
            raise ValueError("Do not replace a whole field and its sections in the same update")
        identity = (field, heading.strip().casefold())
        if identity in seen_sections:
            raise ValueError("Do not change the same section twice")
        seen_sections.add(identity)
        affected.add(field)
        _content_format(section.get("content"))
    for content in text.values():
        _content_format(content)
    if "labels" in spec:
        labels = spec["labels"]
        if not isinstance(labels, dict) or labels.keys() - {"add", "remove"}:
            raise ValueError("labels must contain add and/or remove arrays")
        _labels(labels.get("add", []))
        _labels(labels.get("remove", []))
        if set(labels.get("add", [])) & set(labels.get("remove", [])):
            raise ValueError("Do not add and remove the same label")
        if "labels" in affected:
            raise ValueError("Do not combine label operations with a labels field replacement")
        if labels.get("add") or labels.get("remove"):
            affected.add("labels")
    for field in affected:
        if not FIELD_ID.fullmatch(field) or field in PROTECTED:
            raise ValueError(f"Field {field} is not supported for this operation")
    if not creating and not affected:
        raise ValueError("At least one field change is required")
    return sorted(affected)


def validate_transition_spec(spec: Any) -> list[str]:
    """Accept only whole transition-screen fields and an optional snapshot."""
    if not isinstance(spec, dict):
        raise ValueError("Input must be one JSON object, not a list of issues")
    unknown = spec.keys() - {"expected", "fields", "text"}
    if unknown:
        raise ValueError("Unknown input keys: " + ", ".join(sorted(unknown)))
    fields, text = spec.get("fields", {}), spec.get("text", {})
    if not isinstance(fields, dict) or not isinstance(text, dict):
        raise ValueError("fields and text must be objects")
    if fields.keys() & text.keys():
        raise ValueError("Do not supply a field through both fields and text")
    affected = set(fields) | set(text)
    for field in affected:
        if not FIELD_ID.fullmatch(field) or field in PROTECTED - {"resolution"}:
            raise ValueError(f"Field {field} is not supported for a transition")
    for content in text.values():
        _content_format(content)
    return sorted(affected)


def validate_transition_fields(
    fields: dict[str, Any], metadata: dict[str, Any], current: dict[str, Any],
) -> None:
    """Check supplied values and required transition-screen fields, not editmeta."""
    if "resolution" in fields:
        value = fields["resolution"]
        choices = metadata.get("resolution", {}).get("allowedValues")
        if (not isinstance(value, dict) or set(value) != {"id"}
                or not isinstance(value["id"], str) or not value["id"].isascii()
                or not value["id"].isdecimal() or not isinstance(choices, list)
                or not any(isinstance(choice, dict) and choice.get("id") == value["id"]
                           for choice in choices)):
            raise ValueError("resolution requires an ID offered by this transition screen")
    validate_fields(fields, metadata)
    for field, info in metadata.items():
        if not info["required"]:
            continue
        if field in PROTECTED - {"resolution"} or "set" not in info["operations"]:
            raise ValueError(f"Required transition field {field} uses an unsupported operation")
        if field not in fields and not info.get("hasDefaultValue"):
            if field not in current or current[field] is None or current[field] in ("", [], {}):
                raise ValueError(f"Missing required transition field: {field}")


def build_changes(
    spec: dict[str, Any], metadata: dict[str, Any], current: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return field replacements and label operations. Do not mutate inputs."""
    fields = copy.deepcopy(spec.get("fields", {}))
    for field, content in spec.get("text", {}).items():
        info = metadata.get(field)
        if not isinstance(info, dict):
            raise ValueError(f"Field {field} is not available in this issue context")
        kind, value = _content_format(content)
        if is_rich_text(field, info):
            fields[field] = _document(kind, value)
        elif kind == "text" and info.get("schema", {}).get("type") == "string":
            fields[field] = value
        else:
            raise ValueError(f"Field {field} does not support that text format; check metadata")
    for section in spec.get("sections", []):
        field = section.get("field", "description")
        if not is_rich_text(field, metadata.get(field, {})):
            raise ValueError(f"Field {field} is not a supported rich-text field")
        kind, value = _content_format(section["content"])
        body = _document(kind, value)
        fields[field] = replace_section(
            fields.get(field, current.get(field)), section["heading"], body,
            create=section.get("create", False), level=section.get("level", 2),
        )
    operations: dict[str, Any] = {}
    if "labels" in spec:
        existing = current.get("labels") or []
        _labels(existing)
        changes = []
        for label in spec["labels"].get("add", []):
            if label not in existing:
                changes.append({"add": label})
        for label in spec["labels"].get("remove", []):
            if label in existing:
                changes.append({"remove": label})
        if changes:
            operations["labels"] = changes
    return fields, operations


def validate_fields(
    fields: dict[str, Any], metadata: dict[str, Any], *, creating: bool = False,
) -> None:
    for field, value in fields.items():
        if creating and field in {"project", "issuetype"}:
            continue
        info = metadata.get(field)
        if not isinstance(info, dict) or "set" not in info.get("operations", []):
            raise ValueError(f"Field {field} is not settable in this issue context")
        if value is None:
            if info.get("required"):
                raise ValueError(f"Field {field} is required and cannot be cleared")
            continue
        if info.get("required") and (value == "" or value == []):
            raise ValueError(f"Field {field} is required and cannot be empty")
        if field == "summary" and (not isinstance(value, str) or not value.strip()):
            raise ValueError("summary must be non-empty text")
        if field == "labels":
            _labels(value)
        schema = info.get("schema", {})
        kind = schema.get("type")
        if is_rich_text(field, info):
            validate_document(value)
        elif kind == "string" and not isinstance(value, str):
            raise ValueError(f"Field {field} requires a string")
        elif kind in {"number", "integer"} and (
            type(value) not in {int, float} or (type(value) is float and not math.isfinite(value))
            or (kind == "integer" and type(value) is not int)
        ):
            raise ValueError(f"Field {field} requires a finite {kind}")
        elif kind == "boolean" and type(value) is not bool:
            raise ValueError(f"Field {field} requires a boolean")
        elif kind == "array":
            if not isinstance(value, list):
                raise ValueError(f"Field {field} requires an array")
            if schema.get("items") == "string" and any(not isinstance(item, str) for item in value):
                raise ValueError(f"Field {field} requires an array of strings")
        elif kind in REFERENCE_TYPES or field in REFERENCE_FIELDS:
            if not isinstance(value, dict) or not any(
                isinstance(value.get(key), str) and value[key].strip()
                for key in ("id", "accountId", "key", "value", "name", "groupId")
            ):
                raise ValueError(f"Field {field} requires an object with an explicit identifier")
        choices = info.get("allowedValues")
        if isinstance(choices, list) and choices:
            supplied = value if isinstance(value, list) else [value]
            if any(not any(_choice_matches(item, choice) for choice in choices) for item in supplied):
                raise ValueError(f"Field {field} contains a value not listed in its metadata")
    if creating:
        missing = [field for field, info in metadata.items()
                   if info.get("required") and not info.get("hasDefaultValue") and field not in fields]
        if missing:
            raise ValueError("Missing required create fields: " + ", ".join(sorted(missing)))


def validate_label_operations(operations: dict[str, Any], metadata: dict[str, Any]) -> None:
    supported = metadata.get("labels", {}).get("operations", [])
    for operation in operations.get("labels", []):
        if next(iter(operation)) not in supported:
            raise ValueError("The requested label operation is not available in edit metadata")


def is_rich_text(field: str, info: dict[str, Any]) -> bool:
    custom_type = info.get("schema", {}).get("custom")
    return field in {"description", "environment"} or (
        isinstance(custom_type, str) and custom_type.endswith(":textarea")
    )


def value_matches(
    expected: Any, actual: Any, field: str = "", *, schema: dict[str, Any] | None = None,
) -> bool:
    """Compare full values, allowing extra metadata only on typed references."""
    schema = schema or {}
    if field == "labels" and isinstance(expected, list) and isinstance(actual, list):
        if any(not isinstance(label, str) for label in [*expected, *actual]):
            return False
        return sorted(expected) == sorted(actual)
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        if expected.get("type") == "doc":
            return _normalize_adf(expected) == _normalize_adf(actual)
        reference = schema.get("type") in REFERENCE_TYPES or field in REFERENCE_FIELDS
        if not reference and expected.keys() != actual.keys():
            return False
        child_schema = {"type": "option"} if schema.get("type") == "option" else {}
        return all(key in actual and value_matches(
            value, actual[key], schema=child_schema if key == "child" else None
        ) for key, value in expected.items())
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            return False
        item_schema = {"type": schema.get("items")}
        references = schema.get("items") in REFERENCE_TYPES
        if field in {"components", "versions", "fixVersions"}:
            item_schema = {"type": "component" if field == "components" else "version"}
            references = True
        if references:
            remaining = list(actual)
            for value in expected:
                match = next((index for index, item in enumerate(remaining)
                              if value_matches(value, item, schema=item_schema)), None)
                if match is None:
                    return False
                remaining.pop(match)
            return True
        return all(value_matches(left, right, schema=item_schema)
                   for left, right in zip(expected, actual))
    if type(expected) in {int, float} and type(actual) in {int, float}:
        return expected == actual
    return type(expected) is type(actual) and expected == actual


def _normalize_adf(value: Any) -> Any:
    if isinstance(value, dict):
        result = {key: _normalize_adf(item) for key, item in value.items()}
        if isinstance(result.get("attrs"), dict):
            result["attrs"].pop("localId", None)
            if not result["attrs"]:
                result.pop("attrs")
        if result.get("content") == []:
            result.pop("content")
        return result
    if isinstance(value, list):
        return [_normalize_adf(item) for item in value]
    return value


def _choice_matches(value: Any, choice: Any) -> bool:
    if isinstance(value, dict) and isinstance(choice, dict):
        for key in ("id", "accountId", "key", "value", "name"):
            if key in value:
                return str(value[key]) == str(choice.get(key))
        return False
    return value == choice


def _content_format(content: Any) -> tuple[str, Any]:
    if not isinstance(content, dict) or len(content) != 1:
        raise ValueError("Text content must contain exactly one of text, markdown, or adf")
    kind, value = next(iter(content.items()))
    if kind == "adf":
        validate_document(value)
    elif kind not in {"text", "markdown"} or not isinstance(value, str):
        raise ValueError("Text content must contain text, markdown, or an ADF document")
    return kind, value


def _document(kind: str, value: Any) -> dict[str, Any]:
    if kind == "adf":
        return copy.deepcopy(validate_document(value))
    return from_markdown(value) if kind == "markdown" else from_text(value)


def _labels(value: Any) -> None:
    if (not isinstance(value, list)
            or any(not isinstance(item, str) or not item or any(char.isspace() for char in item)
                   for item in value)):
        raise ValueError("Labels must be an array of non-empty strings without whitespace")
    if len(set(value)) != len(value):
        raise ValueError("Labels must not contain duplicates")
