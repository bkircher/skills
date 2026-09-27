"""Metadata discovery and context isolation without network access."""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from client import JiraClient
from metadata import Metadata


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(spec=JiraClient)
        self.metadata = Metadata(self.client)

    def test_create_type_name_resolves_to_an_id(self):
        self.client.request_object.side_effect = [
            {"startAt": 0, "total": 1, "issueTypes": [{"id": "10001", "name": "Task"}]},
            {"startAt": 0, "total": 1, "fields": [{"fieldId": "summary", "required": True}]},
        ]

        result = self.metadata.for_create("ABC", "Task")

        self.assertEqual(result, {"project": "ABC", "issue_type_id": "10001",
                                  "fields": {"summary": {"fieldId": "summary", "required": True}}})
        self.assertEqual(self.client.request_object.call_count, 2)

    def test_create_metadata_uses_all_pages(self):
        self.client.request_object.side_effect = [
            {"startAt": 0, "total": 2, "fields": [{"fieldId": "summary"}]},
            {"startAt": 1, "total": 2, "fields": [{"fieldId": "description"}]},
        ]

        result = self.metadata.for_create("ABC", "10001")

        self.assertEqual(result["fields"], {"summary": {"fieldId": "summary"},
                                            "description": {"fieldId": "description"}})
        self.client.request_object.assert_called_with(
            "GET", "/rest/api/3/issue/createmeta/ABC/issuetypes/10001?startAt=1&maxResults=100")

    def test_metadata_cache_is_scoped_to_project_and_type(self):
        self.client.request_object.side_effect = [
            {"startAt": 0, "total": 1, "fields": [{"fieldId": "summary"}]},
            {"startAt": 0, "total": 1, "fields": [{"fieldId": "other"}]},
        ]

        first = self.metadata.for_create("ABC", "10001")
        other = self.metadata.for_create("DEF", "10001")
        again = self.metadata.for_create("ABC", "10001")

        self.assertEqual(first, again)
        self.assertEqual(other["project"], "DEF")
        self.assertEqual(self.client.request_object.call_count, 2)

    def test_returned_metadata_cannot_change_the_cache(self):
        self.client.request_object.return_value = {
            "startAt": 0, "total": 1, "fields": [{"fieldId": "summary"}]}

        first = self.metadata.for_create("ABC", "10001")
        first["fields"].clear()
        again = self.metadata.for_create("ABC", "10001")

        self.assertEqual(again["fields"], {"summary": {"fieldId": "summary"}})
        self.assertEqual(self.client.request_object.call_count, 1)

    def test_no_progress_stops_metadata_pagination(self):
        self.client.request_object.return_value = {"startAt": 0, "total": 1, "fields": []}

        with self.assertRaisesRegex(RuntimeError, "no progress"):
            self.metadata.for_create("ABC", "10001")

        self.assertEqual(self.client.request_object.call_count, 1)

    def test_ambiguous_type_name_is_not_guessed(self):
        self.client.request_object.return_value = {"startAt": 0, "total": 2, "issueTypes": [
            {"id": "10001", "name": "Task"}, {"id": "10002", "name": "Task"}]}

        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.metadata.for_create("ABC", "Task")

        self.assertEqual(self.client.request_object.call_count, 1)

    def test_edit_metadata_is_scoped_to_issue(self):
        self.client.request_object.side_effect = [
            {"fields": {"summary": {"required": True}}}, {"fields": {}},
        ]

        first = self.metadata.for_edit("ABC-1")
        second = self.metadata.for_edit("ABC-2")

        self.assertEqual(first, {"summary": {"required": True}})
        self.assertEqual(second, {})
        self.assertEqual(self.client.request_object.call_count, 2)


if __name__ == "__main__":
    unittest.main()
