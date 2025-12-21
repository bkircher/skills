#!/usr/bin/env python3
"""
Jira helpers.

The render_markdown function accepts either a Jira description doc or a Jira
comment object that contains a "body" field.
"""

from __future__ import annotations

from typing import Any


INDENT = "  "


def render_markdown(value: dict[str, Any] | None) -> str:
    """Render a Jira description or comment to Markdown.

    Render Jira rich text (Atlassian Document Format) to Markdown.
    """
    doc = _extract_doc(value)
    if not doc:
        return ""
    renderer = _MarkdownRenderer()
    return renderer.render(doc)


def _extract_doc(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if value.get("type") == "doc":
        return value
    body = value.get("body")
    if isinstance(body, dict) and body.get("type") == "doc":
        return body
    description = value.get("description")
    if isinstance(description, dict) and description.get("type") == "doc":
        return description
    if isinstance(value.get("content"), list) and value.get("version") is not None:
        return value
    return None


class _MarkdownRenderer:
    def render(self, doc: dict[str, Any]) -> str:
        blocks: list[str] = []
        for node in doc.get("content") or []:
            lines = self._render_block(node, list_level=0)
            if not lines:
                continue
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def _render_block(self, node: dict[str, Any], list_level: int) -> list[str]:
        node_type = node.get("type")
        if node_type == "paragraph":
            return self._render_paragraph(node)
        if node_type == "heading":
            return [self._render_heading(node)]
        if node_type == "bulletList":
            return self._render_list(node, list_level, ordered=False)
        if node_type == "orderedList":
            return self._render_list(node, list_level, ordered=True)
        if node_type == "blockquote":
            return self._render_blockquote(node, list_level)
        if node_type == "panel":
            return self._render_panel(node, list_level)
        if node_type == "codeBlock":
            return self._render_code_block(node)
        if node_type == "rule":
            return ["---"]
        if node_type == "table":
            return self._render_table(node)
        text = _collect_text(node)
        return [text] if text else []

    def _render_paragraph(self, node: dict[str, Any]) -> list[str]:
        return _render_paragraph_lines(self, node)

    def _render_heading(self, node: dict[str, Any]) -> str:
        level = node.get("attrs", {}).get("level", 1)
        level = max(1, min(6, int(level)))
        text = "".join(self._render_inline(child) for child in node.get("content") or [])
        return f"{'#' * level} {text}".rstrip()

    def _render_list(self, node: dict[str, Any], list_level: int, ordered: bool) -> list[str]:
        lines: list[str] = []
        start = node.get("attrs", {}).get("order", 1)
        index = int(start) if ordered else 1
        for item in node.get("content") or []:
            lines.extend(self._render_list_item(item, list_level, ordered, index))
            if ordered:
                index += 1
        return lines

    def _render_list_item(
        self, node: dict[str, Any], list_level: int, ordered: bool, index: int
    ) -> list[str]:
        indent = INDENT * list_level
        bullet = f"{index}." if ordered else "-"
        bullet_prefix = f"{indent}{bullet} "
        continuation_prefix = " " * len(bullet_prefix)
        content = node.get("content") or []
        if not content:
            return [bullet_prefix.rstrip()]

        lines: list[str] = []
        first = content[0]
        if first.get("type") == "paragraph":
            paragraph_lines = _render_paragraph_lines(self, first)
            if paragraph_lines:
                lines.append(bullet_prefix + paragraph_lines[0])
                for line in paragraph_lines[1:]:
                    lines.append(continuation_prefix + line)
            else:
                lines.append(bullet_prefix.rstrip())
        else:
            lines.append(bullet_prefix.rstrip())
            lines.extend(self._render_block_in_list(first, list_level, continuation_prefix))

        for block in content[1:]:
            lines.extend(self._render_block_in_list(block, list_level, continuation_prefix))
        return lines

    def _render_block_in_list(
        self, node: dict[str, Any], list_level: int, continuation_prefix: str
    ) -> list[str]:
        node_type = node.get("type")
        if node_type in {"bulletList", "orderedList"}:
            return self._render_block(node, list_level + 1)
        block_lines = self._render_block(node, list_level)
        return [continuation_prefix + line for line in block_lines]

    def _render_blockquote(self, node: dict[str, Any], list_level: int) -> list[str]:
        inner = self._render_inner_blocks(node.get("content") or [], list_level)
        if not inner:
            return [">"]
        return [f"> {line}".rstrip() for line in inner]

    def _render_panel(self, node: dict[str, Any], list_level: int) -> list[str]:
        title = ""
        attrs = node.get("attrs") or {}
        if attrs.get("title"):
            title = f"**{_escape_markdown(str(attrs['title']))}** "
        inner = self._render_inner_blocks(node.get("content") or [], list_level)
        if not inner:
            return [f"> {title}".rstrip()]
        first = [f"> {title}{inner[0]}".rstrip()] if title else [f"> {inner[0]}".rstrip()]
        rest = [f"> {line}".rstrip() for line in inner[1:]]
        return first + rest

    def _render_code_block(self, node: dict[str, Any]) -> list[str]:
        attrs = node.get("attrs") or {}
        language = attrs.get("language") or ""
        code = _collect_text(node)
        fence = f"```{language}" if language else "```"
        lines = code.splitlines() or [""]
        return [fence, *lines, "```"]

    def _render_table(self, node: dict[str, Any]) -> list[str]:
        rows = node.get("content") or []
        if not rows:
            return []

        rendered_rows: list[list[str]] = []
        header_row = False
        for row in rows:
            cells = row.get("content") or []
            rendered_cells = []
            for cell in cells:
                if cell.get("type") == "tableHeader":
                    header_row = True
                cell_lines = self._render_cell(cell)
                rendered_cells.append("<br>".join(cell_lines).strip())
            rendered_rows.append(rendered_cells)

        if not rendered_rows:
            return []

        col_count = max(len(row) for row in rendered_rows)
        first_row = rendered_rows[0]
        lines = ["| " + " | ".join(first_row + [""] * (col_count - len(first_row))) + " |"]
        if header_row:
            lines.append("| " + " | ".join(["---"] * col_count) + " |")
        for row in rendered_rows[1 if header_row else 0 :]:
            lines.append("| " + " | ".join(row + [""] * (col_count - len(row))) + " |")
        return lines

    def _render_cell(self, node: dict[str, Any]) -> list[str]:
        content = node.get("content") or []
        return self._render_inner_blocks(content, list_level=0, tight=True)

    def _render_inner_blocks(
        self, nodes: list[dict[str, Any]], list_level: int, tight: bool = False
    ) -> list[str]:
        blocks: list[str] = []
        for node in nodes:
            lines = self._render_block(node, list_level)
            if not lines:
                continue
            blocks.append("\n".join(lines))
        if not blocks:
            return []
        joined = "\n".join(blocks) if tight else "\n\n".join(blocks)
        return joined.splitlines()

    def _render_inline(self, node: dict[str, Any]) -> str:
        node_type = node.get("type")
        if node_type == "text":
            text = node.get("text") or ""
            marks = node.get("marks") or []
            return _apply_marks(text, marks)
        if node_type == "emoji":
            attrs = node.get("attrs") or {}
            return attrs.get("text") or attrs.get("shortName") or ""
        if node_type == "mention":
            attrs = node.get("attrs") or {}
            text = attrs.get("text") or attrs.get("displayName") or attrs.get("id") or ""
            return f"@{text}" if text else ""
        if node_type == "inlineCard":
            attrs = node.get("attrs") or {}
            url = attrs.get("url") or ""
            return f"<{url}>" if url else ""
        if node_type == "status":
            attrs = node.get("attrs") or {}
            text = attrs.get("text") or ""
            return f"`{_escape_markdown(text)}`" if text else ""
        if node_type == "date":
            attrs = node.get("attrs") or {}
            return attrs.get("text") or attrs.get("timestamp") or ""
        if node_type == "hardBreak":
            return ""
        content = node.get("content")
        if isinstance(content, list):
            return "".join(self._render_inline(child) for child in content)
        if node.get("text"):
            return _escape_markdown(str(node["text"]))
        attrs = node.get("attrs") or {}
        if attrs.get("url"):
            return f"<{attrs['url']}>"
        return ""


def _render_paragraph_lines(renderer: _MarkdownRenderer, node: dict[str, Any]) -> list[str]:
    lines = [""]
    for child in node.get("content") or []:
        if child.get("type") == "hardBreak":
            lines[-1] = lines[-1].rstrip() + "  "
            lines.append("")
            continue
        lines[-1] += renderer._render_inline(child)
    return lines


def _apply_marks(text: str, marks: list[dict[str, Any]]) -> str:
    if not marks:
        return _escape_markdown(text)

    if any(mark.get("type") == "code" for mark in marks):
        escaped = text.replace("`", "\\`")
        return f"`{escaped}`"

    value = _escape_markdown(text)
    for mark in marks:
        mark_type = mark.get("type")
        if mark_type == "strong":
            value = f"**{value}**"
        elif mark_type == "em":
            value = f"*{value}*"
        elif mark_type == "strike":
            value = f"~~{value}~~"
        elif mark_type == "underline":
            value = f"<u>{value}</u>"

    link = next((mark for mark in marks if mark.get("type") == "link"), None)
    if link:
        href = (link.get("attrs") or {}).get("href")
        if href:
            value = f"[{value}]({href})"
    return value


def _escape_markdown(text: str) -> str:
    escaped = text.replace("\\", "\\\\")
    for char in ("`", "*", "_", "~", "[", "]"):
        escaped = escaped.replace(char, f"\\{char}")
    return escaped


def _collect_text(node: dict[str, Any]) -> str:
    if not isinstance(node, dict):
        return ""
    node_type = node.get("type")
    if node_type == "text":
        return node.get("text") or ""
    if node_type == "hardBreak":
        return "\n"
    if node_type in {"emoji", "mention"}:
        attrs = node.get("attrs") or {}
        return attrs.get("text") or attrs.get("shortName") or ""
    content = node.get("content")
    if isinstance(content, list):
        return "".join(_collect_text(child) for child in content)
    return ""
