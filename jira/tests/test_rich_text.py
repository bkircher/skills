"""Tests for new content and lossless preservation of untouched Jira sections."""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from adf import render_markdown
from rich_text import from_markdown, from_text, read_sections, replace_section, validate_document


def existing_document():
    return {
        "type": "doc", "version": 1,
        "content": [
            {"type": "mediaSingle", "attrs": {"layout": "center"}, "content": [
                {"type": "media", "attrs": {"id": "asset-1", "type": "file", "collection": "files"}}
            ]},
            {"type": "heading", "attrs": {"level": 2, "localId": "keep-heading-id"},
             "content": [{"type": "text", "text": "Acceptance criteria", "marks": [{"type": "strong"}]}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "Old criteria"}]},
            {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Links"}]},
            {"type": "paragraph", "content": [{"type": "inlineCard", "attrs": {"url": "https://example.net"}}]},
        ],
    }


class RichTextTests(unittest.TestCase):
    def test_plain_text_keeps_markdown_punctuation_literal(self):
        result = from_text("**literal**\nsecond line")

        self.assertEqual(result, {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [
                {"type": "text", "text": "**literal**"}, {"type": "hardBreak"},
                {"type": "text", "text": "second line"},
            ]}
        ]})

    def test_markdown_builds_headings_and_flat_lists(self):
        result = from_markdown("## Criteria\n\n- First\n- Second")

        self.assertEqual(result, {"type": "doc", "version": 1, "content": [
            {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Criteria"}]},
            {"type": "bulletList", "content": [
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "First"}]}]},
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Second"}]}]},
            ]},
        ]})

    def test_markdown_link_becomes_a_link_mark(self):
        result = from_markdown("[Guide](https://example.net/guide)")

        self.assertEqual(result["content"][0]["content"], [
            {"type": "text", "text": "Guide", "marks": [
                {"type": "link", "attrs": {"href": "https://example.net/guide"}}
            ]}
        ])

    def test_code_block_preserves_literal_content(self):
        result = from_markdown("```python\nprint('**literal**')\n# comment\n```")

        self.assertEqual(result["content"], [{"type": "codeBlock", "attrs": {"language": "python"},
                                             "content": [{"type": "text", "text": "print('**literal**')\n# comment"}]}])

    def test_inline_code_keeps_html_and_markers_literal(self):
        result = from_markdown("Use `<div>~~literal~~</div>` here.")

        self.assertEqual(result["content"][0]["content"], [
            {"type": "text", "text": "Use "},
            {"type": "text", "text": "<div>~~literal~~</div>", "marks": [{"type": "code"}]},
            {"type": "text", "text": " here."},
        ])

    def test_backslash_before_a_letter_is_preserved(self):
        result = from_markdown(r"Use C:\Users\Example.")

        self.assertEqual(result["content"][0]["content"], [
            {"type": "text", "text": r"Use C:\Users\Example."}])

    def test_ordered_list_keeps_start_number(self):
        result = from_markdown("3. Third\n4. Fourth")

        self.assertEqual(render_markdown(result), "3. Third\n4. Fourth")

    def test_inline_marks_are_supported(self):
        result = from_markdown("**bold**, *italic*, and `code`.")

        self.assertEqual(render_markdown(result), "**bold**, *italic*, and `code`.")

    def test_empty_markdown_is_a_valid_empty_paragraph(self):
        result = from_markdown("")

        self.assertEqual(result, {"type": "doc", "version": 1,
                                  "content": [{"type": "paragraph", "content": []}]})

    def test_unclosed_code_fence_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not closed"):
            from_markdown("```python\nprint('hello')")

    def test_unmatched_inline_marker_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unmatched Markdown"):
            from_markdown("**unfinished")

    def test_markdown_table_is_not_silently_flattened(self):
        with self.assertRaisesRegex(ValueError, "Unsupported Markdown"):
            from_markdown("| A | B |\n| --- | --- |")

    def test_table_without_outer_pipes_is_not_silently_flattened(self):
        with self.assertRaisesRegex(ValueError, "Unsupported Markdown"):
            from_markdown("Name | Value\n--- | ---\nOne | Two")

    def test_nested_list_is_not_silently_flattened(self):
        with self.assertRaisesRegex(ValueError, "Unsupported Markdown"):
            from_markdown("- Parent\n  - Child")

    def test_unsafe_link_scheme_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "links must use"):
            from_markdown("[Open](javascript:unsafe)")

    def test_html_is_not_silently_flattened(self):
        with self.assertRaisesRegex(ValueError, "Unsupported Markdown"):
            from_markdown("<div>HTML</div>")

    def test_renderer_keeps_plain_text_custom_fields(self):
        result = render_markdown("Plain acceptance criteria")

        self.assertEqual(result, "Plain acceptance criteria")

    def test_section_edit_keeps_unknown_nodes_and_heading_attributes(self):
        source = existing_document()
        original = copy.deepcopy(source)
        replacement = {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "New criteria"}]}
        ]}

        result = replace_section(source, "Acceptance criteria", replacement)

        self.assertEqual(result["content"][0], original["content"][0])
        self.assertEqual(result["content"][1], original["content"][1])
        self.assertEqual(result["content"][2], {"type": "paragraph", "content": [{"type": "text", "text": "New criteria"}]})
        self.assertEqual(result["content"][3:], original["content"][3:])
        self.assertEqual(source, original)

    def test_section_read_does_not_include_the_next_section(self):
        source = existing_document()

        result = read_sections(source, "Acceptance criteria")

        self.assertEqual(result, [{"heading": "Acceptance criteria", "level": 2,
                                  "document": {"type": "doc", "version": 1, "content": [
                                      {"type": "paragraph", "content": [{"type": "text", "text": "Old criteria"}]}
                                  ]}}])

    def test_missing_section_requires_explicit_creation(self):
        source = existing_document()
        replacement = from_text("Notes")

        with self.assertRaisesRegex(ValueError, "Section not found"):
            replace_section(source, "Notes", replacement)

        self.assertEqual(len(source["content"]), 5)

    def test_explicit_section_creation_appends_without_rewriting_other_nodes(self):
        source = existing_document()
        replacement = from_text("Notes")

        result = replace_section(source, "Notes", replacement, create=True)

        self.assertEqual(result["content"][:5], source["content"])
        self.assertEqual(result["content"][5:], [
            {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Notes"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "Notes"}]},
        ])

    def test_duplicate_heading_is_rejected(self):
        source = from_markdown("## Same\n\nOne\n\n## Same\n\nTwo")
        replacement = from_text("Replacement")

        with self.assertRaisesRegex(ValueError, "ambiguous"):
            replace_section(source, "Same", replacement)

        self.assertEqual(render_markdown(source), "## Same\n\nOne\n\n## Same\n\nTwo")

    def test_replacement_cannot_escape_its_section_level(self):
        source = existing_document()
        replacement = from_markdown("# Outside the section")

        with self.assertRaisesRegex(ValueError, "at or above"):
            replace_section(source, "Acceptance criteria", replacement)

        self.assertEqual(len(source["content"]), 5)

    def test_adf_text_node_must_have_text(self):
        invalid = {"type": "doc", "version": 1, "content": [{"type": "text"}]}

        with self.assertRaisesRegex(ValueError, "non-empty text"):
            validate_document(invalid)

    def test_adf_heading_must_have_a_valid_level(self):
        invalid = {"type": "doc", "version": 1, "content": [
            {"type": "heading", "attrs": {"level": 0}, "content": []}]}

        with self.assertRaisesRegex(ValueError, "level from 1 through 6"):
            validate_document(invalid)

    def test_boolean_is_not_an_adf_version(self):
        with self.assertRaisesRegex(ValueError, "version 1 document"):
            validate_document({"type": "doc", "version": True, "content": []})

    def test_adf_root_must_be_a_document(self):
        with self.assertRaisesRegex(ValueError, "version 1 document"):
            validate_document({"type": "paragraph", "content": []})


if __name__ == "__main__":
    unittest.main()
