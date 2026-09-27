"""Command interface tests with no files, credentials, or network access."""

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from client import JiraClient
from jira import main


class CliTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(spec=JiraClient)
        self.client.base_url = "https://example.atlassian.net"
        factory = patch("jira.JiraClient.from_env", return_value=self.client)
        self.factory = factory.start()
        self.addCleanup(factory.stop)
        self.stdout = io.StringIO()
        output = patch("sys.stdout", self.stdout)
        output.start()
        self.addCleanup(output.stop)
        self.stderr = io.StringIO()
        errors = patch("sys.stderr", self.stderr)
        errors.start()
        self.addCleanup(errors.stop)

    def test_help_does_not_load_credentials(self):
        with self.assertRaises(SystemExit) as raised:
            main(["--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("search,get,update,transitions,transition,create,metadata", self.stdout.getvalue())
        self.factory.assert_not_called()

    def test_get_prints_json(self):
        self.client.request_object.return_value = {"key": "ABC-1", "fields": {"summary": "Example"}}

        code = main(["get", "ABC-1", "--fields", "summary"])

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.stdout.getvalue())["fields"], {"summary": "Example"})
        self.assertEqual(self.stderr.getvalue(), "")
        self.assertEqual(self.client.request_object.call_count, 1)

    def test_comments_only_avoids_an_issue_fields_request(self):
        self.client.request_object.return_value = {"startAt": 0, "total": 0, "comments": []}

        code = main(["get", "ABC-1", "--comments-only"])

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.stdout.getvalue())["comments"]["items"], [])
        self.client.request_object.assert_called_once_with(
            "GET", "/rest/api/3/issue/ABC-1/comment?startAt=0&maxResults=20")

    def test_comments_only_cannot_silently_ignore_a_snapshot_request(self):
        with self.assertRaises(SystemExit) as raised:
            main(["get", "ABC-1", "--comments-only", "--for-update"])

        self.assertEqual(raised.exception.code, 2)
        self.factory.assert_not_called()

    def test_invalid_json_is_rejected_before_loading_credentials(self):
        with patch("sys.stdin", io.StringIO('{"fields":')):
            code = main(["create", "--input", "-"])

        self.assertEqual(code, 2)
        self.assertIn("Invalid input JSON", json.loads(self.stderr.getvalue())["message"])
        self.factory.assert_not_called()

    def test_duplicate_json_keys_are_rejected(self):
        with patch("sys.stdin", io.StringIO('{"fields": {}, "fields": {}}')):
            code = main(["create", "--input", "-"])

        self.assertEqual(code, 2)
        self.assertIn("duplicate key", self.stderr.getvalue())
        self.factory.assert_not_called()

    def test_non_finite_json_numbers_are_rejected(self):
        with patch("sys.stdin", io.StringIO('{"fields": {"customfield_1": NaN}}')):
            code = main(["create", "--input", "-"])

        self.assertEqual(code, 2)
        self.assertIn("non-finite", self.stderr.getvalue())
        self.factory.assert_not_called()

    def test_overflowing_json_exponent_is_rejected(self):
        with patch("sys.stdin", io.StringIO('{"fields": {"customfield_1": 1e9999}}')):
            code = main(["create", "--input", "-"])

        self.assertEqual(code, 2)
        self.assertIn("non-finite", self.stderr.getvalue())
        self.factory.assert_not_called()

    def test_bulk_input_is_rejected_before_loading_credentials(self):
        with patch("sys.stdin", io.StringIO('[{"fields": {}}, {"fields": {}}]')):
            code = main(["create", "--input", "-"])

        self.assertEqual(code, 2)
        self.assertIn("not a list", self.stderr.getvalue())
        self.factory.assert_not_called()

    def test_transition_apply_requires_input_before_credentials(self):
        with self.assertRaises(SystemExit) as raised:
            main(["transition", "ABC-1", "--id", "31"])

        self.assertEqual(raised.exception.code, 2)
        self.factory.assert_not_called()

    def test_transition_requires_exactly_one_selector(self):
        with self.assertRaises(SystemExit) as raised:
            main(["transition", "ABC-1", "--id", "31", "--name", "Finish", "--preview"])

        self.assertEqual(raised.exception.code, 2)
        self.factory.assert_not_called()

    def test_transition_rejects_duplicate_keys_before_credentials(self):
        with patch("sys.stdin", io.StringIO('{"fields": {}, "fields": {}}')):
            code = main(["transition", "ABC-1", "--id", "31", "--preview", "--input", "-"])

        self.assertEqual(code, 2)
        self.assertIn("duplicate key", self.stderr.getvalue())
        self.factory.assert_not_called()

    def test_transition_rejects_non_finite_number_before_credentials(self):
        with patch("sys.stdin", io.StringIO('{"fields": {"customfield_1": NaN}}')):
            code = main(["transition", "ABC-1", "--id", "31", "--preview", "--input", "-"])

        self.assertEqual(code, 2)
        self.assertIn("non-finite", self.stderr.getvalue())
        self.factory.assert_not_called()

    def test_transition_rejects_unsupported_payload_before_credentials(self):
        with patch("sys.stdin", io.StringIO('{"fields": {"status": {"id": "3"}}}')):
            code = main(["transition", "ABC-1", "--id", "31", "--preview", "--input", "-"])

        self.assertEqual(code, 2)
        self.assertIn("not supported", self.stderr.getvalue())
        self.factory.assert_not_called()

    def test_transition_listing_uses_issue_and_transition_reads(self):
        self.client.request_object.side_effect = [
            {"key": "ABC-1", "fields": {"status": {"id": "1", "name": "Open"}}},
            {"transitions": []},
        ]

        code = main(["transitions", "ABC-1"])

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.stdout.getvalue())["transitions"], [])
        self.client.request_json.assert_not_called()

    def test_transition_preview_without_input_returns_snapshot(self):
        self.client.request_object.side_effect = [
            {"transitions": [{"id": "31", "name": "Finish", "to": {"id": "3", "name": "Done"},
                              "fields": {}}]},
            {"key": "ABC-1", "fields": {"status": {"id": "1", "name": "Open"}}},
        ]

        code = main(["transition", "ABC-1", "--to-status", "Done", "--preview"])

        self.assertEqual(code, 0)
        self.assertEqual(list(json.loads(self.stdout.getvalue())["snapshot"]["hashes"]), ["status"])
        self.client.request_json.assert_not_called()

    def test_transition_unknown_has_a_distinct_exit_code(self):
        with patch("sys.stdin", io.StringIO("{}")), patch(
            "jira.JiraIssues.transition", return_value={"status": "unknown", "verified": False}
        ):
            code = main(["transition", "ABC-1", "--id", "31", "--input", "-"])

        self.assertEqual(code, 3)

    def test_transition_conflict_has_a_nonzero_exit_code(self):
        with patch("sys.stdin", io.StringIO("{}")), patch(
            "jira.JiraIssues.transition", return_value={"status": "conflict", "verified": False}
        ):
            code = main(["transition", "ABC-1", "--id", "31", "--input", "-"])

        self.assertEqual(code, 1)

    def test_delete_command_is_not_available(self):
        with self.assertRaises(SystemExit) as raised:
            main(["delete", "ABC-1"])

        self.assertEqual(raised.exception.code, 2)
        self.factory.assert_not_called()

    def test_bulk_command_is_not_available(self):
        with self.assertRaises(SystemExit) as raised:
            main(["bulk", "--input", "-"])

        self.assertEqual(raised.exception.code, 2)
        self.factory.assert_not_called()

    def test_permission_denied_when_reading_input_stops_before_credentials(self):
        with patch("jira.Path.read_text", side_effect=PermissionError("Permission denied")):
            code = main(["create", "--input", "ticket.json"])

        self.assertEqual(code, 1)
        self.assertIn("Permission denied", self.stderr.getvalue())
        self.factory.assert_not_called()

    def test_unknown_write_result_has_a_distinct_exit_code(self):
        result = {"status": "unknown", "operation": "create", "verified": False}

        with patch("sys.stdin", io.StringIO("{}")), patch("jira.JiraIssues.create", return_value=result):
            code = main(["create", "--input", "-"])

        self.assertEqual(code, 3)
        self.assertEqual(json.loads(self.stdout.getvalue()), result)
        self.assertEqual(self.stderr.getvalue(), "")

    def test_conflict_has_a_nonzero_exit_code(self):
        result = {"status": "conflict", "operation": "update", "verified": False}

        with patch("sys.stdin", io.StringIO("{}")), patch("jira.JiraIssues.update", return_value=result):
            code = main(["update", "ABC-1", "--input", "-"])

        self.assertEqual(code, 1)
        self.assertEqual(json.loads(self.stdout.getvalue())["status"], "conflict")

    def test_create_preview_from_a_file_uses_the_shared_client_without_posting(self):
        self.client.request_object.return_value = {"startAt": 0, "total": 1, "fields": [
            {"fieldId": "summary", "required": True, "operations": ["set"], "schema": {"type": "string"}}]}
        text = '{"project": "ABC", "issue_type": "10001", "fields": {"summary": "Example"}}'

        with patch("jira.Path.read_text", return_value=text):
            code = main(["create", "--input", "ticket.json", "--preview"])

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.stdout.getvalue())["status"], "preview")
        self.client.request_object.assert_called_once_with(
            "GET", "/rest/api/3/issue/createmeta/ABC/issuetypes/10001?startAt=0&maxResults=100")
        self.client.request_json.assert_not_called()

    def test_read_errors_use_stderr_without_a_traceback(self):
        self.client.request_object.side_effect = RuntimeError("Connection failed. No retry was made.")

        code = main(["get", "ABC-1"])

        self.assertEqual(code, 1)
        self.assertEqual(self.stdout.getvalue(), "")
        self.assertEqual(json.loads(self.stderr.getvalue()), {
            "status": "error", "message": "Connection failed. No retry was made."})
        self.assertNotIn("Traceback", self.stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
