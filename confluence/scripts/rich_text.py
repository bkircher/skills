"""Build new ADF content and replace sections without converting untouched nodes."""

import copy
import re
import string
import urllib.parse
from typing import Any


HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
LIST_ITEM = re.compile(r"^(?:([-+*])|(\d+)\.)\s+(.+)$")
LINK = re.compile(r"\[([^\[\]\n]+)\]\(([^\s()]+)\)")
HTML = re.compile(r"</?[A-Za-z][^>]*>")
TABLE_RULE = re.compile(r":?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?")


def validate_document(value: Any) -> dict[str, Any]:
    """Check basic ADF structure. Confluence performs full schema validation."""
    if (
        not isinstance(value, dict)
        or value.get("type") != "doc"
        or type(value.get("version")) is not int or value["version"] != 1
        or not isinstance(value.get("content"), list)
    ):
        raise ValueError("ADF must be a version 1 document with a content array")
    _validate_node(value)
    return value


def _validate_node(node: Any) -> None:
    if not isinstance(node, dict) or not isinstance(node.get("type"), str):
        raise ValueError("Each ADF node must have a string type")
    if node["type"] == "text" and (
        not isinstance(node.get("text"), str) or not node["text"]
    ):
        raise ValueError("An ADF text node must contain non-empty text")
    if "content" in node:
        if not isinstance(node["content"], list):
            raise ValueError("ADF content must be an array")
        for child in node["content"]:
            _validate_node(child)
    if "attrs" in node and not isinstance(node["attrs"], dict):
        raise ValueError("ADF attrs must be an object")
    if node["type"] == "heading":
        level = node.get("attrs", {}).get("level")
        if type(level) is not int or not 1 <= level <= 6:
            raise ValueError("An ADF heading needs a level from 1 through 6")
    if "marks" in node and (
        not isinstance(node["marks"], list)
        or any(not isinstance(mark, dict) or not isinstance(mark.get("type"), str)
               for mark in node["marks"])
    ):
        raise ValueError("ADF marks must be an array of typed objects")


def from_text(text: str) -> dict[str, Any]:
    """Build a plain paragraph. Preserve newlines as hard breaks."""
    if not isinstance(text, str):
        raise ValueError("Text content must be a string")
    content: list[dict[str, Any]] = []
    for index, line in enumerate(text.replace("\r\n", "\n").split("\n")):
        if index:
            content.append({"type": "hardBreak"})
        if line:
            content.append({"type": "text", "text": line})
    return {"type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": content}]}


def from_markdown(text: str) -> dict[str, Any]:
    """Read a limited Markdown format, not general Markdown or rendered page text.

    Supported blocks: paragraphs, ATX headings, flat lists, triple-backtick code.
    Supported inline forms: **bold**, *italic*, `code`, and [text](https://url).
    Use text input for literal punctuation, or raw ADF for other rich content.
    """
    if not isinstance(text, str):
        raise ValueError("Markdown content must be a string")
    lines = text.replace("\r\n", "\n").split("\n")
    blocks: list[dict[str, Any]] = []
    paragraph: list[str] = []
    index = 0

    def flush() -> None:
        if paragraph:
            blocks.append({"type": "paragraph", "content": _inline(" ".join(paragraph))})
            paragraph.clear()

    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.strip():
            flush()
            continue
        if line.startswith("```"):
            flush()
            language = line[3:].strip()
            if "`" in language or not re.fullmatch(r"[\w+.-]*", language):
                raise ValueError("Use a triple-backtick code fence with one language name")
            code: list[str] = []
            while index < len(lines) and lines[index] != "```":
                code.append(lines[index])
                index += 1
            if index == len(lines):
                raise ValueError("Markdown code fence is not closed")
            index += 1
            block: dict[str, Any] = {"type": "codeBlock", "content": []}
            if language:
                block["attrs"] = {"language": language}
            if code and "\n".join(code):
                block["content"] = [{"type": "text", "text": "\n".join(code)}]
            blocks.append(block)
            continue
        if (
            line[:1].isspace()
            or line.startswith((">", "|", "~~~"))
            or re.fullmatch(r"(?:---+|===+|\*\*\*+|___+)", line.strip())
            or TABLE_RULE.fullmatch(line.strip())
            or re.match(r"^\[[^]]+\]:", line)
            or re.search(r"\[[ xX]\]\s", line[:8])
        ):
            raise ValueError("Unsupported Markdown block. Use plain text or raw ADF")
        heading = HEADING.fullmatch(line)
        item = LIST_ITEM.fullmatch(line)
        if heading:
            flush()
            blocks.append({"type": "heading", "attrs": {"level": len(heading[1])},
                           "content": _inline(heading[2])})
        elif item:
            flush()
            if item[2] and int(item[2]) < 1:
                raise ValueError("Ordered lists must start at 1 or higher")
            kind = "orderedList" if item[2] else "bulletList"
            if not blocks or blocks[-1]["type"] != kind:
                block = {"type": kind, "content": []}
                if item[2]:
                    block["attrs"] = {"order": int(item[2])}
                blocks.append(block)
            blocks[-1]["content"].append({"type": "listItem", "content": [
                {"type": "paragraph", "content": _inline(item[3])}
            ]})
        else:
            paragraph.append(line)
    flush()
    return {"type": "doc", "version": 1,
            "content": blocks or [{"type": "paragraph", "content": []}]}


def _inline(text: str, marks: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    plain: list[str] = []
    index = 0
    marks = marks or []

    def flush() -> None:
        if plain:
            node: dict[str, Any] = {"type": "text", "text": "".join(plain)}
            if marks:
                node["marks"] = copy.deepcopy(marks)
            nodes.append(node)
            plain.clear()

    while index < len(text):
        if (text[index] == "\\" and index + 1 < len(text)
                and text[index + 1] in string.punctuation):
            plain.append(text[index + 1])
            index += 2
            continue
        if text.startswith(("![", "~~"), index) or HTML.match(text, index):
            raise ValueError("Unsupported Markdown inline content. Use plain text or raw ADF")
        link = LINK.match(text, index)
        if link:
            flush()
            if urllib.parse.urlsplit(link[2]).scheme not in {"https", "http", "mailto"}:
                raise ValueError("Markdown links must use HTTPS, HTTP, or mailto")
            nodes.extend(_inline(link[1], [*marks, {"type": "link", "attrs": {"href": link[2]}}]))
            index = link.end()
            continue
        marker = "**" if text.startswith("**", index) else text[index]
        if marker in {"**", "*", "`"}:
            flush()
            end = text.find(marker, index + len(marker))
            if end < 0 or end == index + len(marker):
                raise ValueError("Unmatched Markdown marker. Escape it or use plain text")
            inner = text[index + len(marker):end]
            if marker == "`":
                if marks:
                    raise ValueError("Nested code marks are not supported; use raw ADF")
                nodes.append({"type": "text", "text": inner, "marks": [{"type": "code"}]})
            else:
                kind = "strong" if marker == "**" else "em"
                nodes.extend(_inline(inner, [*marks, {"type": kind}]))
            index = end + len(marker)
        else:
            plain.append(text[index])
            index += 1
    flush()
    return nodes


def read_sections(value: Any, heading: str) -> list[dict[str, Any]]:
    if value is None or isinstance(value, str):
        return []
    doc = validate_document(value)
    return [
        {"heading": _plain(doc["content"][start]),
         "level": doc["content"][start]["attrs"]["level"],
         "document": {"type": "doc", "version": 1,
                      "content": copy.deepcopy(doc["content"][start + 1:end])}}
        for start, end in _section_spans(doc, heading)
    ]


def replace_section(
    value: Any, heading: str, replacement: dict[str, Any], *,
    create: bool = False, level: int = 2,
) -> dict[str, Any]:
    """Replace one section body. Keep the original heading and all other nodes."""
    if not isinstance(heading, str) or not heading.strip():
        raise ValueError("A section heading is required")
    if type(create) is not bool or type(level) is not int or not 1 <= level <= 6:
        raise ValueError("Section create must be boolean and level must be 1 through 6")
    replacement = validate_document(replacement)
    doc = copy.deepcopy(validate_document(value)) if value is not None else {
        "type": "doc", "version": 1, "content": []
    }
    spans = _section_spans(doc, heading)
    if len(spans) > 1:
        raise ValueError("The section heading is ambiguous; no content was changed")
    if spans:
        start, end = spans[0]
        level = doc["content"][start]["attrs"]["level"]
    elif not create:
        raise ValueError("Section not found. Set create=true only to add a new section")
    else:
        start = len(doc["content"])
        end = start + 1
        doc["content"].append({"type": "heading", "attrs": {"level": level},
                               "content": [{"type": "text", "text": heading}]})
    if any(node.get("type") == "heading" and node.get("attrs", {}).get("level", 1) <= level
           for node in replacement["content"]):
        raise ValueError("Section content must not contain headings at or above its level")
    doc["content"][start + 1:end] = copy.deepcopy(replacement["content"])
    return doc


def _section_spans(doc: dict[str, Any], heading: str) -> list[tuple[int, int]]:
    content = doc["content"]
    spans: list[tuple[int, int]] = []
    for start, node in enumerate(content):
        if node.get("type") != "heading" or _plain(node).strip().casefold() != heading.strip().casefold():
            continue
        level = node.get("attrs", {}).get("level", 1)
        end = start + 1
        while end < len(content):
            following = content[end]
            if following.get("type") == "heading" and following.get("attrs", {}).get("level", 1) <= level:
                break
            end += 1
        spans.append((start, end))
    return spans


def _plain(node: dict[str, Any]) -> str:
    return node.get("text", "") + "".join(_plain(child) for child in node.get("content", []))
