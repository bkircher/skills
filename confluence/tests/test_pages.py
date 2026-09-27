"""Public page commands with a fake Confluence transport."""

import copy
import json
import sys
import unittest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts"))

from client import RequestError  # noqa: E402
from pages import ConfluencePages  # noqa: E402

DOC = {"type": "doc", "version": 1, "content": [
    {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Overview"}]},
    {"type": "extension", "attrs": {"extensionKey": "macro"}},
    {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Next"}]},
    {"type": "paragraph", "content": [{"type": "text", "text": "Keep"}]},
]}
PAGE = {"id": "123", "spaceId": "456", "parentId": "99", "title": "Guide", "status": "current",
        "version": {"number": 3}, "body": {"atlas_doc_format": {"value": json.dumps(DOC)}},
        "labels": {"results": [{"name": "team"}], "meta": {"hasMore": True}}}
SNAPSHOT = {"site": "https://example.atlassian.net", "page_id": "123", "version": 3}


class FakeClient:
    base_url = "https://example.atlassian.net"

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request_object(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return copy.deepcopy(response)


class PageTests(unittest.TestCase):
    def test_get_returns_readable_body_labels_and_snapshot(self):
        client = FakeClient([PAGE])
        pages = ConfluencePages(client)

        result = pages.get("https://example.atlassian.net/wiki/spaces/DEV/pages/123/Guide",
                           raw_adf=True, for_update=True)

        self.assertEqual(result["snapshot"], SNAPSHOT)
        self.assertEqual(result["body_adf"], DOC)
        self.assertTrue(result["labels_have_more"])
        self.assertTrue(result["body_available"])
        self.assertEqual(result["labels"], ["team"])
        self.assertIn("## Overview", result["body_markdown"])

    def test_get_reports_missing_adf_not_empty_page(self):
        page = {**PAGE, "body": {"storage": {"value": "<p>old</p>"}}}
        pages = ConfluencePages(FakeClient([page]))

        result = pages.get("123")

        self.assertFalse(result["body_available"])
        self.assertEqual(result["body_markdown"], "")

    def test_children_follow_same_site_cursor(self):
        client = FakeClient([PAGE, {"results": [{"id": "5", "title": "Child"}],
                                    "_links": {"next": "/wiki/api/v2/pages/123/children?cursor=2"}},
                             {"results": [{"id": "6", "title": "Other"}]}])
        pages = ConfluencePages(client)

        result = pages.get("123", children=True)

        self.assertEqual([child["id"] for child in result["children"]], ["5", "6"])
        self.assertEqual(client.calls[2][1], "/wiki/api/v2/pages/123/children?cursor=2")

    def test_search_quotes_user_query_and_reports_limit(self):
        client = FakeClient([{"results": [{"content": {"id": "123", "title": "Guide"}}],
                              "_links": {"next": "/rest/api/search?cursor=2"}}])
        pages = ConfluencePages(client)

        result = pages.search('a" OR type = "blogpost', space="DEV", limit=1)

        self.assertEqual(len(result["results"]), 1)
        self.assertTrue(result["has_more"])
        self.assertIn("%5C%22", client.calls[0][1])
        self.assertIn("space+%3D+%22DEV%22", client.calls[0][1])

    def test_external_pagination_is_rejected(self):
        client = FakeClient([{"results": [], "_links": {"next": "https://attacker.example/wiki/api/v2/pages"}}])
        pages = ConfluencePages(client)

        with self.assertRaisesRegex(ValueError, "unsafe pagination"):
            pages.search("guide")

        self.assertEqual(len(client.calls), 1)

    def test_repeated_search_cursor_stops(self):
        client = FakeClient([{"results": [], "_links": {"next": "/rest/api/search?cursor=2"}},
                             {"results": [], "_links": {"next": "/rest/api/search?cursor=2"}}])
        pages = ConfluencePages(client)

        with self.assertRaisesRegex(RuntimeError, "repeated a pagination link"):
            pages.search("guide")

        self.assertEqual(len(client.calls), 2)

    def test_cross_site_page_url_is_rejected_before_request(self):
        client = FakeClient([])
        pages = ConfluencePages(client)

        with self.assertRaisesRegex(ValueError, "ATLASSIAN_URL"):
            pages.get("https://other.atlassian.net/wiki/spaces/DEV/pages/123/Guide")

        self.assertEqual(client.calls, [])

    def test_update_section_keeps_unmodified_macros_and_uses_next_version(self):
        saved = {**PAGE, "version": {"number": 4}}
        change = {"expected": SNAPSHOT, "section": {"heading": "Next", "content": {"text": "New"}}}
        doc = {**DOC, "content": [*DOC["content"][:3],
                                {"type": "paragraph", "content": [{"type": "text", "text": "New"}]}]}
        saved["body"] = {"atlas_doc_format": {"value": json.dumps(doc)}}
        client = FakeClient([PAGE, {}, saved])
        pages = ConfluencePages(client)

        result = pages.update("123", change)

        self.assertEqual(result["status"], "updated")
        self.assertTrue(result["verified"])
        self.assertEqual(client.calls[1][2]["version"], {"number": 4})
        self.assertEqual(json.loads(client.calls[1][2]["body"]["value"]), doc)
        self.assertEqual(client.calls[1][2]["body"]["representation"], "atlas_doc_format")

    def test_ambiguous_section_does_not_write(self):
        duplicate = {**DOC, "content": [*DOC["content"], DOC["content"][0]]}
        page = {**PAGE, "body": {"atlas_doc_format": {"value": json.dumps(duplicate)}}}
        client = FakeClient([page])
        pages = ConfluencePages(client)

        with self.assertRaisesRegex(ValueError, "ambiguous"):
            pages.update("123", {"expected": SNAPSHOT, "section": {
                "heading": "Overview", "content": {"text": "New"}}})

        self.assertEqual([method for method, _, _ in client.calls], ["GET"])

    def test_update_requires_snapshot_before_any_request(self):
        client = FakeClient([])
        pages = ConfluencePages(client)

        with self.assertRaisesRegex(ValueError, "expected must be"):
            pages.update("123", {"title": "New"})

        self.assertEqual(client.calls, [])

    def test_stale_snapshot_does_not_write(self):
        client = FakeClient([PAGE])
        pages = ConfluencePages(client)

        result = pages.update("123", {"expected": {**SNAPSHOT, "version": 2}, "title": "New"})

        self.assertEqual(result["status"], "conflict")
        self.assertEqual([method for method, _, _ in client.calls], ["GET"])

    def test_server_version_conflict_is_reported(self):
        client = FakeClient([PAGE, RequestError(409, "https://example.atlassian.net/wiki/api/v2/pages/123", "Conflict")])
        pages = ConfluencePages(client)

        result = pages.update("123", {"expected": SNAPSHOT, "title": "New"})

        self.assertEqual(result["status"], "conflict")
        self.assertEqual(len(client.calls), 2)

    def test_draft_page_is_not_published_by_update(self):
        client = FakeClient([{**PAGE, "status": "draft"}])
        pages = ConfluencePages(client)

        with self.assertRaisesRegex(ValueError, "published pages"):
            pages.update("123", {"expected": SNAPSHOT, "title": "New"})

        self.assertEqual([method for method, _, _ in client.calls], ["GET"])

    def test_null_section_is_rejected(self):
        client = FakeClient([])
        pages = ConfluencePages(client)

        with self.assertRaisesRegex(ValueError, "Expected one object"):
            pages.update("123", {"expected": SNAPSHOT, "section": None})

        self.assertEqual(client.calls, [])

    def test_title_only_update_preserves_raw_body(self):
        saved = {**PAGE, "title": "New", "version": {"number": 4}}
        client = FakeClient([PAGE, {}, saved])
        pages = ConfluencePages(client)

        result = pages.update("123", {"expected": SNAPSHOT, "title": "New"})

        self.assertTrue(result["verified"])
        self.assertEqual(json.loads(client.calls[1][2]["body"]["value"]), DOC)

    def test_missing_adf_prevents_update(self):
        page = {**PAGE, "body": {"storage": {"value": "<p>old</p>"}}}
        client = FakeClient([page])
        pages = ConfluencePages(client)

        with self.assertRaisesRegex(ValueError, "no valid ADF body"):
            pages.update("123", {"expected": SNAPSHOT, "title": "New"})

        self.assertEqual([method for method, _, _ in client.calls], ["GET"])

    def test_create_preview_does_not_call_api(self):
        client = FakeClient([])
        pages = ConfluencePages(client)

        result = pages.create({"space_id": "456", "title": "Guide", "body": {"text": "Hello"}}, preview=True)

        self.assertEqual(result["status"], "preview")
        self.assertEqual(client.calls, [])

    def test_create_rejects_noncanonical_space_id(self):
        client = FakeClient([])
        pages = ConfluencePages(client)

        with self.assertRaisesRegex(ValueError, "positive numeric ID"):
            pages.create({"space_id": "000456", "title": "Guide", "body": {"text": "Hello"}})

        self.assertEqual(client.calls, [])

    def test_create_verifies_read_back(self):
        doc = {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]}]}
        saved = {**PAGE, "body": {"atlas_doc_format": {"value": json.dumps(doc)}}}
        client = FakeClient([{"id": "123"}, saved])
        pages = ConfluencePages(client)

        result = pages.create({"space_id": "456", "parent_id": "99", "title": "Guide",
                               "body": {"text": "Hello"}})

        self.assertEqual(result["status"], "created")
        self.assertTrue(result["verified"])
        self.assertEqual(client.calls[0][2]["spaceId"], "456")
        self.assertEqual(client.calls[0][2]["parentId"], "99")

    def test_create_transport_error_is_unknown_not_retried(self):
        client = FakeClient([RuntimeError("timeout")])
        pages = ConfluencePages(client)

        result = pages.create({"space_id": "456", "title": "Guide", "body": {"text": "Hello"}})

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(len(client.calls), 1)

    def test_create_rejection_is_reported(self):
        client = FakeClient([RequestError(403, "https://example.atlassian.net/wiki/api/v2/pages", "Denied")])
        pages = ConfluencePages(client)

        result = pages.create({"space_id": "456", "title": "Guide", "body": {"text": "Hello"}})

        self.assertEqual(result["status"], "rejected")
        self.assertFalse(result["verified"])

    def test_successful_write_with_failed_read_back_is_unverified(self):
        client = FakeClient([{"id": "123"}, RuntimeError("read failed")])
        pages = ConfluencePages(client)

        result = pages.create({"space_id": "456", "title": "Guide", "body": {"text": "Hello"}})

        self.assertEqual(result["status"], "unverified")
        self.assertEqual(len(client.calls), 2)

    def test_update_preview_returns_snapshot_without_write(self):
        client = FakeClient([PAGE])
        pages = ConfluencePages(client)

        result = pages.update("123", {"title": "New"}, preview=True)

        self.assertEqual(result["snapshot"], SNAPSHOT)
        self.assertEqual(result["status"], "preview")
        self.assertEqual([method for method, _, _ in client.calls], ["GET"])

    def test_unsupported_markdown_rejected_before_create(self):
        client = FakeClient([])
        pages = ConfluencePages(client)

        with self.assertRaisesRegex(ValueError, "Unsupported Markdown"):
            pages.create({"space_id": "456", "title": "Guide", "body": {"markdown": "| table |"}})

        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
