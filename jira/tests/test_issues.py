"""Public Jira operations with simulated API responses and write outcomes."""

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from client import JiraClient, RequestError
from issues import JiraIssues


BASE_URL = "https://example.atlassian.net"


def editable_fields():
    return {
        "summary": {"required": True, "operations": ["set"], "schema": {"type": "string"}},
        "description": {"operations": ["set"], "schema": {"type": "string", "system": "description"}},
        "labels": {"operations": ["set", "add", "remove"], "schema": {"type": "array", "items": "string"}},
        "customfield_10010": {"operations": ["set"], "schema": {
            "type": "string", "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield"}},
    }


def issue(fields):
    return {"key": "ABC-123", "fields": fields, "editmeta": {"fields": editable_fields()}}


def summary_snapshot():
    return {"site": BASE_URL, "issue": "ABC-123", "hashes": {
        "summary": "sha256:546c4765179fef0214aa55c65c88435908f99acb5a0e77bd3709c4fc6c62a38c"}}


def labels_snapshot():
    return {"site": BASE_URL, "issue": "ABC-123", "hashes": {
        "labels": "sha256:8db132bc00e6874e6de27c1a6ea41ab59d0068522f5867b272074282a2f10e27"}}


def create_metadata():
    return {"startAt": 0, "maxResults": 100, "total": 1, "fields": [
        {"fieldId": "summary", "name": "Summary", "required": True,
         "operations": ["set"], "schema": {"type": "string"}},
    ]}


def create_spec():
    return {"project": "ABC", "issue_type": "10001", "fields": {"summary": "New issue"}}


class JiraIssuesTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(spec=JiraClient)
        self.client.base_url = BASE_URL
        self.client.request_json.return_value = None
        self.service = JiraIssues(self.client)

    def test_search_returns_a_bounded_page_and_cursor(self):
        self.client.request_object.return_value = {
            "issues": [issue({"summary": "Found"})], "isLast": False, "nextPageToken": "next-page"}

        result = self.service.search(project="ABC", limit=1)

        self.assertEqual(result["count"], 1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["next_page_token"], "next-page")
        self.assertEqual(result["issues"][0]["url"], BASE_URL + "/browse/ABC-123")
        self.client.request_object.assert_called_once_with("POST", "/rest/api/3/search/jql", {
            "jql": 'project = "ABC" ORDER BY updated DESC',
            "fields": ["summary", "status", "assignee", "priority", "labels", "updated"], "maxResults": 1,
        })
        self.client.request_array.assert_not_called()

    def test_search_combines_assignee_and_open_category_filters(self):
        self.client.request_object.return_value = {"issues": [], "isLast": True}

        result = self.service.search(assignee="me", open_only=True)

        self.assertEqual(result["jql"], 'assignee = currentUser() AND statusCategory != "Done" ORDER BY updated DESC')
        self.assertFalse(result["truncated"])

    def test_search_quotes_text_instead_of_inserting_jql_operators(self):
        self.client.request_object.return_value = {"issues": [], "isLast": True}

        result = self.service.search(text='a" OR project = SECRET')

        self.assertEqual(result["jql"], 'text ~ "a\\" OR project = SECRET" ORDER BY updated DESC')

    def test_search_paginates_inside_one_operation(self):
        self.client.request_object.side_effect = [
            {"issues": [issue({"summary": "First"})], "isLast": False, "nextPageToken": "second"},
            {"issues": [{"key": "ABC-124", "fields": {"summary": "Second"}}], "isLast": True},
        ]

        result = self.service.search(jql="project = ABC", fields=["summary"], limit=2)

        self.assertEqual(result["count"], 2)
        self.assertFalse(result["truncated"])
        self.client.request_object.assert_called_with("POST", "/rest/api/3/search/jql", {
            "jql": "project = ABC", "fields": ["summary"], "maxResults": 1, "nextPageToken": "second"})

    def test_search_stops_on_a_repeated_cursor(self):
        self.client.request_object.side_effect = [
            {"issues": [issue({})], "isLast": False, "nextPageToken": "same"},
            {"issues": [issue({})], "isLast": False, "nextPageToken": "same"},
        ]

        with self.assertRaisesRegex(RuntimeError, "no progress"):
            self.service.search(jql="project = ABC", limit=3)

        self.assertEqual(self.client.request_object.call_count, 2)

    def test_search_does_not_mix_jql_and_filters(self):
        with self.assertRaisesRegex(ValueError, "not both"):
            self.service.search(jql="project = ABC", project="DEF")

        self.client.request_object.assert_not_called()

    def test_get_selected_fields_needs_one_request_and_no_catalog(self):
        self.client.request_object.return_value = issue({"summary": "Old summary", "labels": ["keep"]})

        result = self.service.get("ABC-123", fields=["summary", "labels"])

        self.assertEqual(result["fields"], {"summary": "Old summary", "labels": ["keep"]})
        self.assertEqual(result["missing_fields"], [])
        self.assertEqual(self.client.request_object.call_count, 1)
        self.client.request_array.assert_not_called()

    def test_get_returns_a_site_and_issue_bound_snapshot(self):
        self.client.request_object.return_value = issue({"summary": "Old summary"})

        result = self.service.get("ABC-123", fields=["summary"], for_update=True)

        self.assertEqual(result["snapshot"], summary_snapshot())

    def test_get_reports_omitted_fields(self):
        self.client.request_object.return_value = issue({"summary": "Old summary"})

        result = self.service.get("ABC-123", fields=["summary", "customfield_10010"])

        self.assertEqual(result["missing_fields"], ["customfield_10010"])
        self.assertNotIn("customfield_10010", result["fields"])

    def test_get_rejects_an_issue_url_from_another_site(self):
        with self.assertRaisesRegex(ValueError, "another site"):
            self.service.get("https://other.atlassian.net/browse/ABC-123")

        self.client.request_object.assert_not_called()

    def test_get_rejects_embedded_partial_comments(self):
        with self.assertRaisesRegex(ValueError, "--comments"):
            self.service.get("ABC-123", fields=["comment"])

        self.client.request_object.assert_not_called()

    def test_get_returns_readable_text_and_optional_original_adf(self):
        document = {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]}]}
        self.client.request_object.return_value = issue({"description": document})

        result = self.service.get("ABC-123", fields=["description"], raw_adf=True)

        self.assertEqual(result["fields"]["description"], "Hello")
        self.assertEqual(result["raw_adf"], {"description": document})
        self.assertEqual(result["rich_text_fields"], ["description"])

    def test_explicit_acceptance_field_does_not_discover_all_fields(self):
        self.client.request_object.return_value = issue({"description": None, "customfield_10010": "Plain criteria"})

        result = self.service.get("ABC-123", fields=["description"], acceptance_field="customfield_10010")

        self.assertEqual(result["acceptance_criteria"]["sources"], [
            {"field": "customfield_10010", "markdown": "Plain criteria"}])
        self.assertTrue(result["acceptance_criteria"]["custom_fields_checked"])
        self.client.request_array.assert_not_called()

    def test_acceptance_discovery_keeps_all_exact_matches_separate(self):
        self.client.request_array.return_value = [
            {"id": "customfield_10010", "name": "Acceptance criteria"},
            {"id": "customfield_10011", "name": "Acceptance Criteria"},
            {"id": "customfield_10012", "name": "Old acceptance criteria"},
        ]
        self.client.request_object.return_value = issue({
            "description": None, "customfield_10010": "First", "customfield_10011": "Second"})

        result = self.service.get("ABC-123", fields=["description"], acceptance_criteria=True)

        self.assertEqual(result["acceptance_criteria"]["sources"], [
            {"field": "customfield_10010", "markdown": "First"},
            {"field": "customfield_10011", "markdown": "Second"},
        ])
        self.client.request_array.assert_called_once_with("GET", "/rest/api/3/field")

    def test_comments_report_truncation(self):
        self.client.request_object.return_value = {
            "startAt": 0, "total": 2, "comments": [{"id": "1", "body": "Comment"}]}

        result = self.service.comments("ABC-123", limit=1)

        self.assertEqual(result["items"][0]["body_markdown"], "Comment")
        self.assertTrue(result["truncated"])
        self.assertEqual(result["next_start_at"], 1)
        self.assertEqual(self.client.request_object.call_count, 1)

    def test_comments_pagination_stops_if_server_does_not_advance(self):
        self.client.request_object.return_value = {"startAt": 0, "total": 2, "comments": []}

        with self.assertRaisesRegex(RuntimeError, "no progress"):
            self.service.comments("ABC-123")

        self.assertEqual(self.client.request_object.call_count, 1)

    def test_update_requires_a_snapshot_before_any_request(self):
        with self.assertRaisesRegex(ValueError, "requires expected"):
            self.service.update("ABC-123", {"fields": {"summary": "New summary"}})

        self.client.request_object.assert_not_called()
        self.client.request_json.assert_not_called()

    def test_update_rejects_a_snapshot_for_another_issue(self):
        snapshot = summary_snapshot()
        snapshot["issue"] = "ABC-999"

        with self.assertRaisesRegex(ValueError, "this site and issue"):
            self.service.update("ABC-123", {"fields": {"summary": "New summary"}, "expected": snapshot})

        self.client.request_object.assert_not_called()
        self.client.request_json.assert_not_called()

    def test_update_snapshot_must_cover_every_affected_field(self):
        with self.assertRaisesRegex(ValueError, "every affected field"):
            self.service.update("ABC-123", {"fields": {"summary": "New summary", "labels": []},
                                            "expected": summary_snapshot()})

        self.client.request_object.assert_not_called()
        self.client.request_json.assert_not_called()

    def test_update_stops_on_a_stale_snapshot(self):
        self.client.request_object.return_value = issue({"summary": "Changed by someone else"})

        result = self.service.update("ABC-123", {"fields": {"summary": "New summary"}, "expected": summary_snapshot()})

        self.assertEqual(result["status"], "conflict")
        self.assertEqual(self.client.request_object.call_count, 1)
        self.client.request_json.assert_not_called()

    def test_update_preview_returns_a_diff_and_snapshot_without_writing(self):
        self.client.request_object.return_value = issue({"summary": "Old summary"})

        result = self.service.update("ABC-123", {"fields": {"summary": "New summary"}}, preview=True)

        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["snapshot"], summary_snapshot())
        self.assertIn("-Old summary", result["changes"]["summary"]["diff"])
        self.assertIn("+New summary", result["changes"]["summary"]["diff"])
        self.client.request_json.assert_not_called()

    def test_update_sends_only_changed_fields_and_verifies_them(self):
        self.client.request_object.side_effect = [
            issue({"summary": "Old summary"}), issue({"summary": "New summary"})]

        result = self.service.update("ABC-123", {"fields": {"summary": "New summary"}, "expected": summary_snapshot()})

        self.assertEqual(result["status"], "updated")
        self.assertTrue(result["verified"])
        self.assertEqual(result["changed_fields"], ["summary"])
        self.client.request_json.assert_called_once_with("PUT", "/rest/api/3/issue/ABC-123", {
            "fields": {"summary": "New summary"}})
        self.assertEqual(self.client.request_object.call_count, 2)
        self.client.request_object.assert_any_call(
            "GET", "/rest/api/3/issue/ABC-123?fields=summary&expand=editmeta")
        self.client.request_object.assert_called_with("GET", "/rest/api/3/issue/ABC-123?fields=summary")

    def test_unchanged_update_does_not_send_a_write(self):
        self.client.request_object.return_value = issue({"summary": "Old summary"})

        result = self.service.update("ABC-123", {"fields": {"summary": "Old summary"}, "expected": summary_snapshot()})

        self.assertEqual(result["status"], "unchanged")
        self.assertTrue(result["verified"])
        self.client.request_json.assert_not_called()
        self.assertEqual(self.client.request_object.call_count, 1)

    def test_label_operations_do_not_replace_unrelated_labels(self):
        self.client.request_object.side_effect = [
            issue({"labels": ["keep", "remove"]}), issue({"labels": ["keep", "added", "concurrent"]})]

        result = self.service.update("ABC-123", {
            "labels": {"add": ["added"], "remove": ["remove"]}, "expected": labels_snapshot()})

        self.assertTrue(result["verified"])
        self.client.request_json.assert_called_once_with("PUT", "/rest/api/3/issue/ABC-123", {
            "update": {"labels": [{"add": "added"}, {"remove": "remove"}]}})

    def test_read_then_section_update_preserves_unrelated_adf_and_verifies(self):
        original = {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [
                {"type": "inlineCard", "attrs": {"url": "https://example.net/keep"}}]},
            {"type": "heading", "attrs": {"level": 2, "localId": "original-id"},
             "content": [{"type": "text", "text": "Acceptance criteria"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "Old criteria"}]},
        ]}
        saved = copy.deepcopy(original)
        saved["content"][2] = {"type": "paragraph", "content": [{"type": "text", "text": "New criteria"}]}
        self.client.request_object.side_effect = [
            issue({"description": original}), issue({"description": original}), issue({"description": saved})]

        source = self.service.get("ABC-123", fields=["description"], for_update=True)
        result = self.service.update("ABC-123", {
            "expected": source["snapshot"], "sections": [
                {"heading": "Acceptance criteria", "content": {"text": "New criteria"}}
            ]})

        self.assertEqual(result["status"], "updated")
        self.assertTrue(result["verified"])
        self.client.request_json.assert_called_once_with("PUT", "/rest/api/3/issue/ABC-123", {
            "fields": {"description": saved}})
        self.assertEqual(self.client.request_object.call_count, 3)
        self.assertEqual(original["content"][2], {
            "type": "paragraph", "content": [{"type": "text", "text": "Old criteria"}]})

    def test_update_refuses_an_omitted_source_field(self):
        self.client.request_object.return_value = issue({})

        with self.assertRaisesRegex(ValueError, "omitted an affected field"):
            self.service.update("ABC-123", {"fields": {"summary": "New summary"}, "expected": summary_snapshot()})

        self.client.request_json.assert_not_called()

    def test_update_does_not_guess_an_uneditable_field(self):
        self.client.request_object.return_value = {
            "key": "ABC-123", "fields": {"summary": "Old summary"}, "editmeta": {"fields": {}}}

        with self.assertRaisesRegex(ValueError, "not settable"):
            self.service.update("ABC-123", {"fields": {"summary": "New summary"}, "expected": summary_snapshot()})

        self.client.request_json.assert_not_called()

    def test_update_cannot_change_status_as_an_ordinary_field(self):
        with self.assertRaisesRegex(ValueError, "not supported"):
            self.service.update("ABC-123", {"fields": {"status": {"id": "3"}}}, preview=True)

        self.client.request_object.assert_not_called()
        self.client.request_json.assert_not_called()

    def test_update_cannot_combine_whole_field_and_section_replacements(self):
        spec = {"text": {"description": {"text": "New text"}}, "sections": [
            {"heading": "Criteria", "content": {"text": "New criteria"}}]}

        with self.assertRaisesRegex(ValueError, "whole field"):
            self.service.update("ABC-123", spec, preview=True)

        self.client.request_json.assert_not_called()

    def test_successful_write_with_mismatched_content_is_unverified(self):
        self.client.request_object.side_effect = [issue({"summary": "Old summary"}), issue({"summary": "Unexpected"})]

        result = self.service.update("ABC-123", {"fields": {"summary": "New summary"}, "expected": summary_snapshot()})

        self.assertEqual(result["status"], "unverified")
        self.assertTrue(result["write_accepted"])
        self.assertFalse(result["verified"])
        self.assertEqual(result["mismatched_fields"], ["summary"])
        self.assertEqual(self.client.request_json.call_count, 1)

    def test_verification_permission_failure_does_not_repeat_the_write(self):
        self.client.request_object.side_effect = [
            issue({"summary": "Old summary"}), RequestError(403, BASE_URL, "Permission denied")]

        result = self.service.update("ABC-123", {"fields": {"summary": "New summary"}, "expected": summary_snapshot()})

        self.assertEqual(result["status"], "unverified")
        self.assertTrue(result["write_accepted"])
        self.assertEqual(self.client.request_json.call_count, 1)
        self.assertEqual(self.client.request_object.call_count, 2)

    def test_write_permission_failure_stops_without_verification_or_retry(self):
        self.client.request_object.return_value = issue({"summary": "Old summary"})
        self.client.request_json.side_effect = RequestError(403, BASE_URL, "Permission denied")

        result = self.service.update("ABC-123", {"fields": {"summary": "New summary"}, "expected": summary_snapshot()})

        self.assertEqual(result["status"], "rejected")
        self.assertEqual(self.client.request_json.call_count, 1)
        self.assertEqual(self.client.request_object.call_count, 1)

    def test_write_timeout_is_unknown_and_is_not_retried(self):
        self.client.request_object.return_value = issue({"summary": "Old summary"})
        self.client.request_json.side_effect = RuntimeError("Connection timed out")

        result = self.service.update("ABC-123", {"fields": {"summary": "New summary"}, "expected": summary_snapshot()})

        self.assertEqual(result["status"], "unknown")
        self.assertIn("Do not repeat", result["message"])
        self.assertEqual(self.client.request_json.call_count, 1)
        self.assertEqual(self.client.request_object.call_count, 1)

    def test_create_with_known_type_id_needs_metadata_write_and_verification_only(self):
        self.client.request_object.side_effect = [
            create_metadata(), {"key": "ABC-124", "id": "10124"},
            {"key": "ABC-124", "fields": {"summary": "New issue", "project": {"key": "ABC", "id": "10000"},
                                           "issuetype": {"id": "10001", "name": "Task"}}},
        ]

        result = self.service.create(create_spec())

        self.assertEqual(result["status"], "created")
        self.assertTrue(result["verified"])
        self.assertEqual(result["url"], BASE_URL + "/browse/ABC-124")
        self.assertEqual(self.client.request_object.call_count, 3)
        self.client.request_object.assert_any_call("POST", "/rest/api/3/issue", {"fields": {
            "summary": "New issue", "project": {"key": "ABC"}, "issuetype": {"id": "10001"}}})

    def test_create_builds_adf_and_verifies_rich_text(self):
        document = {"type": "doc", "version": 1, "content": [
            {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Acceptance criteria"}]},
            {"type": "bulletList", "content": [{"type": "listItem", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Works"}]}]}]},
        ]}
        self.client.request_object.side_effect = [
            {"startAt": 0, "total": 2, "fields": [
                {"fieldId": "summary", "required": True, "operations": ["set"], "schema": {"type": "string"}},
                {"fieldId": "description", "operations": ["set"], "schema": {"type": "string"}},
            ]},
            {"key": "ABC-124"},
            {"key": "ABC-124", "fields": {
                "summary": "New issue", "description": document,
                "project": {"key": "ABC"}, "issuetype": {"id": "10001"}}},
        ]
        spec = create_spec()
        spec["text"] = {"description": {"markdown": "## Acceptance criteria\n\n- Works"}}

        result = self.service.create(spec)

        self.assertEqual(result["status"], "created")
        self.assertTrue(result["verified"])
        self.client.request_object.assert_any_call("POST", "/rest/api/3/issue", {"fields": {
            "summary": "New issue", "description": document,
            "project": {"key": "ABC"}, "issuetype": {"id": "10001"}}})
        self.assertEqual(self.client.request_object.call_count, 3)

    def test_create_verifies_custom_options_with_extra_server_metadata(self):
        self.client.request_object.side_effect = [
            {"startAt": 0, "total": 2, "fields": [
                {"fieldId": "summary", "required": True, "operations": ["set"], "schema": {"type": "string"}},
                {"fieldId": "customfield_10010", "operations": ["set"], "schema": {"type": "option"},
                 "allowedValues": [{"id": "1", "value": "Red"}]},
            ]},
            {"key": "ABC-124"},
            {"key": "ABC-124", "fields": {
                "summary": "New issue", "customfield_10010": {"id": "1", "value": "Red", "self": "https://example.net/1"},
                "project": {"key": "ABC"}, "issuetype": {"id": "10001"}}},
        ]
        spec = create_spec()
        spec["fields"]["customfield_10010"] = {"id": "1"}

        result = self.service.create(spec)

        self.assertEqual(result["status"], "created")
        self.assertTrue(result["verified"])
        self.assertEqual(self.client.request_object.call_count, 3)

    def test_create_metadata_failure_stops_before_posting(self):
        self.client.request_object.side_effect = RequestError(403, BASE_URL, "Permission denied")

        with self.assertRaisesRegex(RequestError, "Permission denied"):
            self.service.create(create_spec())

        self.assertEqual(self.client.request_object.call_count, 1)
        self.client.request_json.assert_not_called()

    def test_create_preview_does_not_publish(self):
        self.client.request_object.return_value = create_metadata()

        result = self.service.create(create_spec(), preview=True)

        self.assertEqual(result["status"], "preview")
        self.client.request_object.assert_called_once_with(
            "GET", "/rest/api/3/issue/createmeta/ABC/issuetypes/10001?startAt=0&maxResults=100")
        self.client.request_json.assert_not_called()

    def test_create_reports_missing_required_custom_fields_before_posting(self):
        self.client.request_object.return_value = {"startAt": 0, "total": 2, "fields": [
            {"fieldId": "summary", "required": True, "operations": ["set"], "schema": {"type": "string"}},
            {"fieldId": "customfield_10010", "required": True, "operations": ["set"]},
        ]}

        with self.assertRaisesRegex(ValueError, "Missing required create fields: customfield_10010"):
            self.service.create(create_spec())

        self.assertEqual(self.client.request_object.call_count, 1)
        self.client.request_json.assert_not_called()

    def test_create_timeout_does_not_create_again_or_search_automatically(self):
        self.client.request_object.side_effect = [create_metadata(), RuntimeError("Connection timed out")]

        result = self.service.create(create_spec())

        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["verified"])
        self.assertEqual(self.client.request_object.call_count, 2)

    def test_create_without_a_returned_key_is_unknown(self):
        self.client.request_object.side_effect = [create_metadata(), {"id": "10124"}]

        result = self.service.create(create_spec())

        self.assertEqual(result["status"], "unknown")
        self.assertIn("Do not create again", result["message"])
        self.assertEqual(self.client.request_object.call_count, 2)

    def test_create_rejects_bulk_input_before_requests(self):
        with self.assertRaisesRegex(ValueError, "not a list"):
            self.service.create([create_spec(), create_spec()])

        self.client.request_object.assert_not_called()

    def test_create_rejects_unknown_payload_actions(self):
        spec = create_spec()
        spec["transition"] = {"id": "10"}

        with self.assertRaisesRegex(ValueError, "Unknown input keys"):
            self.service.create(spec)

        self.client.request_object.assert_not_called()


def workflow_issue(status_name="Open", status_id="1", **fields):
    return issue({"status": {"id": status_id, "name": status_name}, "resolution": None, **fields})


def workflow(fields=None):
    return {"transitions": [{"id": "31", "name": "Finish issue",
                             "to": {"id": "3", "name": "Done", "statusCategory": {"name": "Done"}},
                             "fields": {} if fields is None else fields}]}


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(spec=JiraClient)
        self.client.base_url = BASE_URL
        self.client.request_json.return_value = None
        self.service = JiraIssues(self.client)

    def test_listing_shows_current_status_screen_and_status_snapshot(self):
        screen = {"resolution": {"required": True, "operations": ["set"],
                                 "schema": {"type": "resolution"}, "hasDefaultValue": False,
                                 "allowedValues": [{"id": "10000", "name": "Done"}]}}
        self.client.request_object.side_effect = [workflow_issue(), workflow(screen)]

        result = self.service.transitions("ABC-123")

        self.assertEqual(result["current_status"], {"id": "1", "name": "Open"})
        self.assertEqual(result["transitions"], [{"id": "31", "name": "Finish issue",
                                                  "to": {"id": "3", "name": "Done"}, "fields": screen}])
        self.assertEqual(result["snapshot"]["issue"], "ABC-123")
        self.assertEqual(list(result["snapshot"]["hashes"]), ["status"])
        self.client.request_object.assert_any_call(
            "GET", "/rest/api/3/issue/ABC-123/transitions?expand=transitions.fields")
        self.client.request_json.assert_not_called()

    def test_listing_uses_canonical_key_when_jira_moved_the_issue(self):
        self.client.request_object.side_effect = [
            {"key": "ABC-124", "fields": {"status": {"id": "1", "name": "Open"}}}, workflow()]

        result = self.service.transitions("ABC-123")

        self.assertEqual(result["key"], "ABC-124")
        self.assertEqual(result["snapshot"]["issue"], "ABC-124")
        self.client.request_object.assert_called_with(
            "GET", "/rest/api/3/issue/ABC-124/transitions?expand=transitions.fields")

    def test_no_permission_lists_no_available_transitions(self):
        self.client.request_object.side_effect = [workflow_issue(), {"transitions": []}]

        result = self.service.transitions("ABC-123")

        self.assertEqual(result["transitions"], [])

    def test_selector_names_are_exact_case_insensitive_and_do_not_use_category(self):
        self.client.request_object.side_effect = [workflow(), workflow_issue()]

        result = self.service.transition("ABC-123", name="finish ISSUE", preview=True)

        self.assertEqual(result["transition"]["id"], "31")
        self.assertEqual(result["before_status"], {"id": "1", "name": "Open"})
        self.assertEqual(result["target_status"], {"id": "3", "name": "Done"})
        self.client.request_json.assert_not_called()

    def test_target_name_selects_exact_status_not_category(self):
        self.client.request_object.side_effect = [workflow(), workflow_issue()]

        result = self.service.transition("ABC-123", to_status="done", preview=True)

        self.assertEqual(result["transition"]["id"], "31")

    def test_missing_selector_does_not_write(self):
        self.client.request_object.return_value = workflow()

        with self.assertRaisesRegex(ValueError, "unavailable or ambiguous"):
            self.service.transition("ABC-123", to_status="Closed", preview=True)

        self.client.request_json.assert_not_called()

    def test_status_category_is_not_a_selector(self):
        self.client.request_object.return_value = {"transitions": [
            {"id": "31", "name": "Close", "to": {"id": "3", "name": "Closed",
                                                    "statusCategory": {"name": "Done"}}, "fields": {}}]}

        with self.assertRaisesRegex(ValueError, "unavailable or ambiguous"):
            self.service.transition("ABC-123", to_status="Done", preview=True)

        self.client.request_json.assert_not_called()

    def test_duplicate_target_names_are_ambiguous(self):
        self.client.request_object.return_value = {"transitions": [
            {"id": "31", "name": "Finish", "to": {"id": "3", "name": "Done"}, "fields": {}},
            {"id": "32", "name": "Resolve", "to": {"id": "3", "name": "Done"}, "fields": {}}]}

        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.service.transition("ABC-123", to_status="Done", preview=True)

        self.client.request_json.assert_not_called()

    def test_duplicate_action_names_are_ambiguous(self):
        self.client.request_object.return_value = {"transitions": [
            {"id": "31", "name": "Finish", "to": {"id": "3", "name": "Done"}, "fields": {}},
            {"id": "32", "name": "finish", "to": {"id": "4", "name": "Closed"}, "fields": {}}]}

        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.service.transition("ABC-123", name="FINISH", preview=True)

        self.client.request_json.assert_not_called()

    def test_duplicate_ids_are_ambiguous(self):
        self.client.request_object.return_value = {"transitions": [
            {"id": "31", "name": "Finish", "to": {"id": "3", "name": "Done"}, "fields": {}},
            {"id": "31", "name": "Close", "to": {"id": "4", "name": "Closed"}, "fields": {}}]}

        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.service.transition("ABC-123", transition_id="31", preview=True)

        self.client.request_json.assert_not_called()

    def test_self_loop_is_rejected_before_post(self):
        self.client.request_object.side_effect = [workflow(), workflow_issue("Done", "3")]

        with self.assertRaisesRegex(ValueError, "Self-loop"):
            self.service.transition("ABC-123", transition_id="31", preview=True)

        self.client.request_json.assert_not_called()

    def test_malformed_screen_metadata_is_not_used(self):
        self.client.request_object.return_value = workflow({"resolution": {"required": True}})

        with self.assertRaisesRegex(RuntimeError, "transition-screen metadata"):
            self.service.transition("ABC-123", transition_id="31", preview=True)

        self.client.request_json.assert_not_called()

    def test_transition_requires_snapshot_before_requests(self):
        with self.assertRaisesRegex(ValueError, "requires expected"):
            self.service.transition("ABC-123", {}, transition_id="31")

        self.client.request_object.assert_not_called()

    def test_stale_status_returns_conflict_without_post(self):
        self.client.request_object.side_effect = [workflow(), workflow_issue()]
        preview = self.service.transition("ABC-123", transition_id="31", preview=True)
        self.client.reset_mock()
        self.client.request_object.side_effect = [workflow(), workflow_issue("In Progress", "2")]

        result = self.service.transition("ABC-123", {"expected": preview["snapshot"]}, transition_id="31")

        self.assertEqual(result["status"], "conflict")
        self.client.request_json.assert_not_called()

    def test_stale_field_returns_conflict_without_post(self):
        screen = {"summary": {"required": False, "operations": ["set"], "schema": {"type": "string"}}}
        self.client.request_object.side_effect = [workflow(screen), workflow_issue(summary="old")]
        preview = self.service.transition("ABC-123", {"fields": {"summary": "new"}},
                                          transition_id="31", preview=True)
        self.client.reset_mock()
        self.client.request_object.side_effect = [workflow(screen), workflow_issue(summary="other")]

        result = self.service.transition("ABC-123", {"expected": preview["snapshot"],
                                                     "fields": {"summary": "new"}}, transition_id="31")

        self.assertEqual(result["status"], "conflict")
        self.client.request_json.assert_not_called()

    def test_source_issue_key_changed_returns_conflict(self):
        self.client.request_object.side_effect = [workflow(), workflow_issue()]
        preview = self.service.transition("ABC-123", transition_id="31", preview=True)
        self.client.reset_mock()
        self.client.request_object.side_effect = [workflow(),
                                                  {"key": "ABC-124", "fields": {
                                                      "status": {"id": "1", "name": "Open"}}}]

        result = self.service.transition("ABC-123", {"expected": preview["snapshot"]}, transition_id="31")

        self.assertEqual(result["status"], "conflict")
        self.client.request_json.assert_not_called()

    def test_unavailable_transition_after_status_change_is_conflict(self):
        self.client.request_object.side_effect = [workflow(), workflow_issue()]
        preview = self.service.transition("ABC-123", transition_id="31", preview=True)
        self.client.reset_mock()
        self.client.request_object.side_effect = [{"transitions": []}, workflow_issue("Done", "3")]

        result = self.service.transition("ABC-123", {"expected": preview["snapshot"]}, transition_id="31")

        self.assertEqual(result["status"], "conflict")
        self.client.request_json.assert_not_called()

    def test_missing_required_resolution_stops_before_post(self):
        screen = {"resolution": {"required": True, "operations": ["set"],
                                 "schema": {"type": "resolution"},
                                 "allowedValues": [{"id": "10000", "name": "Done"}]}}
        self.client.request_object.side_effect = [workflow(screen), workflow_issue()]

        with self.assertRaisesRegex(ValueError, "Missing required transition field: resolution"):
            self.service.transition("ABC-123", transition_id="31", preview=True)

        self.client.request_json.assert_not_called()

    def test_resolution_not_offered_on_screen_stops_before_post(self):
        self.client.request_object.side_effect = [workflow(), workflow_issue()]

        with self.assertRaisesRegex(ValueError, "ID offered"):
            self.service.transition("ABC-123", {"fields": {"resolution": {"id": "10000"}}},
                                    transition_id="31", preview=True)

        self.client.request_json.assert_not_called()

    def test_required_text_field_with_invalid_type_stops_before_post(self):
        screen = {"customfield_1": {"required": True, "operations": ["set"],
                                    "schema": {"type": "string"}}}
        self.client.request_object.side_effect = [workflow(screen), workflow_issue(customfield_1=None)]

        with self.assertRaisesRegex(ValueError, "requires a string"):
            self.service.transition("ABC-123", {"fields": {"customfield_1": 7}},
                                    transition_id="31", preview=True)

        self.client.request_json.assert_not_called()

    def test_resolution_preview_includes_supplied_field_and_snapshot(self):
        screen = {"resolution": {"required": True, "operations": ["set"],
                                 "schema": {"type": "resolution"},
                                 "allowedValues": [{"id": "10000", "name": "Done"}]}}
        self.client.request_object.side_effect = [workflow(screen), workflow_issue()]

        result = self.service.transition("ABC-123", {"fields": {"resolution": {"id": "10000"}}},
                                         transition_id="31", preview=True)

        self.assertEqual(result["changes"]["resolution"], {"before": None, "after": {"id": "10000"}})
        self.assertEqual(set(result["snapshot"]["hashes"]), {"status", "resolution"})
        self.client.request_json.assert_not_called()

    def test_text_screen_field_builds_adf_and_verifies(self):
        screen = {"description": {"required": True, "operations": ["set"],
                                  "schema": {"type": "string"}}}
        self.client.request_object.side_effect = [workflow(screen), workflow_issue(description=None)]
        spec = {"text": {"description": {"text": "Done"}}}
        preview = self.service.transition("ABC-123", spec, transition_id="31", preview=True)
        self.client.reset_mock()
        document = {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Done"}]}]}
        self.client.request_object.side_effect = [workflow(screen), workflow_issue(description=None),
                                                  workflow_issue("Done", "3", description=document)]

        result = self.service.transition("ABC-123", {**spec, "expected": preview["snapshot"]},
                                         transition_id="31")

        self.assertEqual(result["status"], "transitioned")
        self.client.request_json.assert_called_once_with(
            "POST", "/rest/api/3/issue/ABC-123/transitions",
            {"transition": {"id": "31"}, "fields": {"description": document}})

    def test_204_transition_without_fields_posts_once_and_reads_back_resolution(self):
        self.client.request_object.side_effect = [workflow(), workflow_issue()]
        preview = self.service.transition("ABC-123", transition_id="31", preview=True)
        self.client.reset_mock()
        self.client.request_object.side_effect = [workflow(), workflow_issue(),
                                                  workflow_issue("Done", "3")]

        result = self.service.transition("ABC-123", {"expected": preview["snapshot"]},
                                         transition_id="31")

        self.assertEqual(result["status"], "transitioned")
        self.assertTrue(result["verified"])
        self.assertIsNone(result["observed_resolution"])
        self.client.request_json.assert_called_once_with(
            "POST", "/rest/api/3/issue/ABC-123/transitions", {"transition": {"id": "31"}})
        self.client.request_object.assert_called_with(
            "GET", "/rest/api/3/issue/ABC-123?fields=status%2Cresolution")

    def test_resolution_with_extra_jira_metadata_verifies_by_id(self):
        screen = {"resolution": {"required": True, "operations": ["set"],
                                 "schema": {"type": "resolution"},
                                 "allowedValues": [{"id": "10000", "name": "Done"}]}}
        self.client.request_object.side_effect = [workflow(screen), workflow_issue()]
        preview = self.service.transition("ABC-123", {"fields": {"resolution": {"id": "10000"}}},
                                          transition_id="31", preview=True)
        self.client.reset_mock()
        self.client.request_object.side_effect = [workflow(screen), workflow_issue(),
                                                  workflow_issue("Done", "3", resolution={
                                                      "id": "10000", "name": "Done"})]

        result = self.service.transition("ABC-123", {"expected": preview["snapshot"],
                                                     "fields": {"resolution": {"id": "10000"}}},
                                         transition_id="31")

        self.assertEqual(result["status"], "transitioned")
        self.assertEqual(result["observed_resolution"], {"id": "10000", "name": "Done"})
        self.client.request_json.assert_called_once_with(
            "POST", "/rest/api/3/issue/ABC-123/transitions",
            {"transition": {"id": "31"}, "fields": {"resolution": {"id": "10000"}}})

    def test_readback_missing_resolution_is_unverified(self):
        self.client.request_object.side_effect = [workflow(), workflow_issue()]
        preview = self.service.transition("ABC-123", transition_id="31", preview=True)
        self.client.reset_mock()
        self.client.request_object.side_effect = [workflow(), workflow_issue(),
                                                  issue({"status": {"id": "3", "name": "Done"}})]

        result = self.service.transition("ABC-123", {"expected": preview["snapshot"]},
                                         transition_id="31")

        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["mismatched_fields"], ["resolution"])

    def test_readback_status_mismatch_is_unverified(self):
        self.client.request_object.side_effect = [workflow(), workflow_issue()]
        preview = self.service.transition("ABC-123", transition_id="31", preview=True)
        self.client.reset_mock()
        self.client.request_object.side_effect = [workflow(), workflow_issue(), workflow_issue()]

        result = self.service.transition("ABC-123", {"expected": preview["snapshot"]},
                                         transition_id="31")

        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["mismatched_fields"], ["status"])
        self.client.request_json.assert_called_once()

    def test_readback_field_mismatch_is_unverified(self):
        screen = {"summary": {"required": False, "operations": ["set"], "schema": {"type": "string"}}}
        self.client.request_object.side_effect = [workflow(screen), workflow_issue(summary="old")]
        preview = self.service.transition("ABC-123", {"fields": {"summary": "new"}},
                                          transition_id="31", preview=True)
        self.client.reset_mock()
        self.client.request_object.side_effect = [workflow(screen), workflow_issue(summary="old"),
                                                  workflow_issue("Done", "3", summary="other")]

        result = self.service.transition("ABC-123", {"expected": preview["snapshot"],
                                                     "fields": {"summary": "new"}}, transition_id="31")

        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["mismatched_fields"], ["summary"])

    def test_permission_rejection_is_not_retried(self):
        self.client.request_object.side_effect = [workflow(), workflow_issue()]
        preview = self.service.transition("ABC-123", transition_id="31", preview=True)
        self.client.reset_mock()
        self.client.request_object.side_effect = [workflow(), workflow_issue()]
        self.client.request_json.side_effect = RequestError(403, BASE_URL, "Denied")

        result = self.service.transition("ABC-123", {"expected": preview["snapshot"]},
                                         transition_id="31")

        self.assertEqual(result["status"], "rejected")
        self.client.request_json.assert_called_once()
        self.assertEqual(self.client.request_object.call_count, 2)

    def test_timeout_has_unknown_outcome_without_retry(self):
        self.client.request_object.side_effect = [workflow(), workflow_issue()]
        preview = self.service.transition("ABC-123", transition_id="31", preview=True)
        self.client.reset_mock()
        self.client.request_object.side_effect = [workflow(), workflow_issue()]
        self.client.request_json.side_effect = RuntimeError("Timed out")

        result = self.service.transition("ABC-123", {"expected": preview["snapshot"]},
                                         transition_id="31")

        self.assertEqual(result["status"], "unknown")
        self.client.request_json.assert_called_once()
        self.assertEqual(self.client.request_object.call_count, 2)

    def test_readback_failure_is_unverified_without_retry(self):
        self.client.request_object.side_effect = [workflow(), workflow_issue()]
        preview = self.service.transition("ABC-123", transition_id="31", preview=True)
        self.client.reset_mock()
        self.client.request_object.side_effect = [workflow(), workflow_issue(), RuntimeError("Read failed")]

        result = self.service.transition("ABC-123", {"expected": preview["snapshot"]},
                                         transition_id="31")

        self.assertEqual(result["status"], "unverified")
        self.assertTrue(result["write_accepted"])
        self.client.request_json.assert_called_once()


if __name__ == "__main__":
    unittest.main()
