"""Test the Jira client without network access or real credentials."""

import email
import io
import os
import sys
import traceback
import unittest
import urllib.error
import urllib.response
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from client import JiraClient, RequestError, extract_issue_key


BASE_URL = "https://example.atlassian.net"
ISSUE_PATH = "/rest/api/3/issue/ABC-123"
ISSUE_URL = "https://example.atlassian.net/rest/api/3/issue/ABC-123"
AUTH = "Basic dXNlcjp0b2tlbg=="


def response(
    body: bytes = b"{}",
    status: int = 200,
    headers: str = "Content-Type: application/json\n",
) -> urllib.response.addinfourl:
    result = urllib.response.addinfourl(
        io.BytesIO(body), email.message_from_string(headers), ISSUE_URL, status
    )
    result.msg = "Test response"
    return result


class JiraClientTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

        proxies = patch("urllib.request.getproxies", return_value={})
        proxies.start()
        self.addCleanup(proxies.stop)

        https = patch("urllib.request.HTTPSHandler.https_open", autospec=True)
        self.https = https.start()
        self.addCleanup(https.stop)
        self.https.return_value = response()
        self.addCleanup(self.https.return_value.close)

        http = patch(
            "urllib.request.HTTPHandler.http_open",
            side_effect=AssertionError("An HTTP request must not be sent"),
        )
        http.start()
        self.addCleanup(http.stop)

        sleep = patch("client.time.sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

        clock = patch("client.time.time", return_value=1735689600.0)
        clock.start()
        self.addCleanup(clock.stop)

        self.client = JiraClient(BASE_URL, AUTH)

    def test_issue_key_accepts_a_single_letter_project(self):
        result = extract_issue_key("A-1")

        self.assertEqual(result, "A-1")

    def test_issue_key_accepts_a_browse_url(self):
        result = extract_issue_key("https://example.atlassian.net/browse/ABC-123")

        self.assertEqual(result, "ABC-123")

    def test_issue_key_rejects_multiple_targets(self):
        with self.assertRaisesRegex(ValueError, "one issue key"):
            extract_issue_key("ABC-123,ABC-456")

        self.https.assert_not_called()

    def test_read_returns_object(self):
        self.https.return_value = response(b'{"key": "ABC-123"}')

        result = self.client.request_object("GET", ISSUE_PATH)

        self.assertEqual(result, {"key": "ABC-123"})
        self.assertEqual(self.https.call_count, 1)

    def test_request_uses_configured_site_authentication_and_timeout(self):
        client = JiraClient("  HTTPS://EXAMPLE.atlassian.net/  ", AUTH, timeout=7)

        client.request_json("get", ISSUE_PATH)

        request = self.https.call_args.args[1]
        self.assertEqual(request.full_url, ISSUE_URL)
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Authorization"), AUTH)
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(request.timeout, 7)
        self.assertEqual(client.base_url, BASE_URL)

    def test_default_timeout_is_thirty_seconds(self):
        self.client.request_json("GET", ISSUE_PATH)

        self.assertEqual(self.https.call_args.args[1].timeout, 30.0)

    def test_search_sends_json_payload(self):
        payload = {"jql": "assignee = currentUser()"}

        self.client.request_object("POST", "/rest/api/3/search/jql", payload)

        request = self.https.call_args.args[1]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.data, b'{"jql": "assignee = currentUser()"}')
        self.assertEqual(request.get_header("Content-type"), "application/json")

    def test_read_returns_array(self):
        self.https.return_value = response(b'[{"id": "description"}]')

        result = self.client.request_array("GET", "/rest/api/3/field")

        self.assertEqual(result, [{"id": "description"}])

    def test_empty_update_success_returns_none(self):
        self.https.return_value = response(b"", 204)

        result = self.client.request_json("PUT", ISSUE_PATH, {"fields": {}})

        self.assertIsNone(result)
        self.assertEqual(self.https.call_count, 1)

    def test_transition_post_accepts_204_without_replay(self):
        self.https.return_value = response(b"", 204)

        result = self.client.request_json("POST", ISSUE_PATH + "/transitions",
                                          {"transition": {"id": "31"}})

        self.assertIsNone(result)
        self.assertEqual(self.https.call_count, 1)
        self.assertEqual(self.https.call_args.args[1].get_method(), "POST")
        self.assertEqual(self.https.call_args.args[1].data, b'{"transition": {"id": "31"}}')

    def test_empty_success_returns_none(self):
        self.https.return_value = response(b"")

        result = self.client.request_json("GET", ISSUE_PATH)

        self.assertIsNone(result)

    def test_object_request_rejects_empty_success(self):
        self.https.return_value = response(b"", 204)

        with self.assertRaisesRegex(RuntimeError, "Expected a JSON object"):
            self.client.request_object("GET", ISSUE_PATH)

        self.assertEqual(self.https.call_count, 1)

    def test_object_request_rejects_array(self):
        self.https.return_value = response(b"[]")

        with self.assertRaisesRegex(RuntimeError, "Expected a JSON object"):
            self.client.request_object("GET", ISSUE_PATH)

        self.assertEqual(self.https.call_count, 1)

    def test_array_request_rejects_object(self):
        self.https.return_value = response(b"{}")

        with self.assertRaisesRegex(RuntimeError, "Expected a JSON array"):
            self.client.request_array("GET", ISSUE_PATH)

        self.assertEqual(self.https.call_count, 1)

    def test_json_null_is_not_an_empty_response(self):
        self.https.return_value = response(b"null")

        with self.assertRaisesRegex(RuntimeError, "Expected a JSON object or array"):
            self.client.request_json("GET", ISSUE_PATH)

        self.assertEqual(self.https.call_count, 1)

    def test_invalid_json_does_not_expose_response_body(self):
        self.https.return_value = response(b"<html>token</html>")

        with self.assertRaises(RuntimeError) as raised:
            self.client.request_json("GET", ISSUE_PATH)

        diagnostic = "".join(traceback.format_exception(raised.exception))
        self.assertIn("invalid JSON", diagnostic)
        self.assertNotIn("token", diagnostic)
        self.assertNotIn("<html>", diagnostic)
        self.assertEqual(self.https.call_count, 1)

    def test_invalid_utf8_has_a_clear_error(self):
        self.https.return_value = response(b"\xff")

        with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
            self.client.request_json("GET", ISSUE_PATH)

        self.assertEqual(self.https.call_count, 1)

    def test_http_site_is_rejected_before_sending_credentials(self):
        with self.assertRaisesRegex(ValueError, "HTTPS site URL"):
            JiraClient("http://example.atlassian.net", AUTH)

        self.https.assert_not_called()

    def test_site_with_credentials_is_rejected_without_exposing_them(self):
        with self.assertRaises(ValueError) as raised:
            JiraClient("https://user:token@example.atlassian.net", AUTH)

        self.assertNotIn("token", str(raised.exception))
        self.https.assert_not_called()

    def test_ticket_url_is_not_accepted_as_site_url(self):
        with self.assertRaisesRegex(ValueError, "Do not include"):
            JiraClient("https://example.atlassian.net/browse/ABC-123", AUTH)

        self.https.assert_not_called()

    def test_site_query_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Do not include"):
            JiraClient("https://example.atlassian.net?token=token", AUTH)

        self.https.assert_not_called()

    def test_site_fragment_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Do not include"):
            JiraClient("https://example.atlassian.net#fragment", AUTH)

        self.https.assert_not_called()

    def test_site_without_hostname_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTPS site URL"):
            JiraClient("https:///", AUTH)

        self.https.assert_not_called()

    def test_invalid_site_port_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTPS site URL"):
            JiraClient("https://example.atlassian.net:invalid", AUTH)

        self.https.assert_not_called()

    def test_control_character_in_site_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTPS site URL"):
            JiraClient("https://example.\natlassian.net", AUTH)

        self.https.assert_not_called()

    def test_absolute_request_url_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "relative API path"):
            self.client.request_json("GET", "https://other.atlassian.net/rest/api/3/field")

        self.https.assert_not_called()

    def test_network_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "relative API path"):
            self.client.request_json("GET", "//other.atlassian.net/rest/api/3/field")

        self.https.assert_not_called()

    def test_request_control_character_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "relative API path"):
            self.client.request_json("GET", "/rest/api/3/field\n")

        self.https.assert_not_called()

    def test_request_fragment_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "relative API path"):
            self.client.request_json("GET", ISSUE_PATH + "#fragment")

        self.https.assert_not_called()

    def test_zero_timeout_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timeout"):
            JiraClient(BASE_URL, AUTH, timeout=0)

        self.https.assert_not_called()

    def test_infinite_timeout_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timeout"):
            JiraClient(BASE_URL, AUTH, timeout=float("inf"))

        self.https.assert_not_called()

    def test_negative_retry_count_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "max_retries"):
            JiraClient(BASE_URL, AUTH, max_retries=-1)

        self.https.assert_not_called()

    def test_authentication_header_cannot_contain_line_breaks(self):
        with self.assertRaisesRegex(ValueError, "authentication header"):
            JiraClient(BASE_URL, AUTH + "\r\nX-Test: value")

        self.https.assert_not_called()

    def test_cross_site_redirect_stops_with_canonical_site_guidance(self):
        self.https.return_value = response(
            b"", 302, "Location: https://canonical.atlassian.net/rest/api/3/issue/ABC-123\n"
        )

        with self.assertRaises(RequestError) as raised:
            self.client.request_json("GET", ISSUE_PATH)

        self.assertEqual(raised.exception.status, 302)
        self.assertIn("https://canonical.atlassian.net", str(raised.exception))
        self.assertIn("Verify the proposed site", str(raised.exception))
        self.assertIn("ATLASSIAN_URL", str(raised.exception))
        self.assertEqual(self.https.call_count, 1)
        self.sleep.assert_not_called()

    def test_same_site_redirect_is_not_followed(self):
        self.https.return_value = response(b"", 301, "Location: /rest/api/3/issue/ABC-456\n")

        with self.assertRaisesRegex(RequestError, "Redirect refused"):
            self.client.request_json("GET", ISSUE_PATH)

        self.assertEqual(self.https.call_count, 1)

    def test_update_302_redirect_has_site_guidance_without_a_replay(self):
        self.https.return_value = response(
            b"", 302, "Location: https://canonical.atlassian.net/rest/api/3/issue/ABC-123\n"
        )

        with self.assertRaises(RequestError) as raised:
            self.client.request_json("PUT", ISSUE_PATH, {"fields": {}})

        self.assertEqual(raised.exception.status, 302)
        self.assertIn("https://canonical.atlassian.net", str(raised.exception))
        self.assertIn("ATLASSIAN_URL", str(raised.exception))
        self.assertEqual(self.https.call_count, 1)
        self.sleep.assert_not_called()

    def test_update_redirect_is_not_replayed(self):
        self.https.return_value = response(
            b"", 307, "Location: https://canonical.atlassian.net/rest/api/3/issue/ABC-123\n"
        )

        with self.assertRaises(RequestError) as raised:
            self.client.request_json("PUT", ISSUE_PATH, {"fields": {}})

        self.assertEqual(raised.exception.status, 307)
        self.assertEqual(self.https.call_count, 1)

    def test_search_redirect_does_not_change_post_to_get(self):
        self.https.return_value = response(b"", 303, "Location: /rest/api/3/search/jql\n")

        with self.assertRaises(RequestError) as raised:
            self.client.request_json("POST", "/rest/api/3/search/jql", {"jql": ""})

        self.assertEqual(raised.exception.status, 303)
        self.assertEqual(self.https.call_count, 1)
        self.assertEqual(self.https.call_args.args[1].get_method(), "POST")

    def test_https_downgrade_redirect_is_not_followed(self):
        self.https.return_value = response(
            b"", 302, "Location: http://example.atlassian.net/rest/api/3/issue/ABC-123\n"
        )

        with self.assertRaisesRegex(RequestError, "canonical HTTPS site URL"):
            self.client.request_json("GET", ISSUE_PATH)

        self.assertEqual(self.https.call_count, 1)

    def test_redirect_diagnostics_omit_url_credentials_and_queries(self):
        self.https.return_value = response(
            b"token", 302, "Location: https://user:token@other.atlassian.net/?token=token\n"
        )

        with self.assertRaises(RequestError) as raised:
            self.client.request_json("GET", ISSUE_PATH)

        diagnostic = "".join(traceback.format_exception(raised.exception))
        self.assertNotIn("token", diagnostic)
        self.assertNotIn("user:", diagnostic)
        self.assertEqual(self.https.call_count, 1)

    def test_read_retries_a_temporary_service_failure(self):
        self.https.side_effect = [response(b"Unavailable", 503), response(b'{"key": "ABC-123"}')]

        result = self.client.request_object("GET", ISSUE_PATH)

        self.assertEqual(result, {"key": "ABC-123"})
        self.assertEqual(self.https.call_count, 2)
        self.sleep.assert_called_once_with(1.0)

    def test_search_post_can_retry_and_honors_retry_after_seconds(self):
        self.https.side_effect = [
            response(b"Slow down", 429, "Retry-After: 5\n"),
            response(b'{"issues": []}'),
        ]

        result = self.client.request_object("POST", "/rest/api/3/search/jql", {"jql": ""})

        self.assertEqual(result, {"issues": []})
        self.assertEqual(self.https.call_count, 2)
        self.sleep.assert_called_once_with(5.0)

    def test_retry_after_http_date_is_honored(self):
        self.https.side_effect = [
            response(b"Slow down", 429, "Retry-After: Wed, 01 Jan 2025 00:00:05 GMT\n"),
            response(),
        ]

        result = self.client.request_json("GET", ISSUE_PATH)

        self.assertEqual(result, {})
        self.sleep.assert_called_once_with(5.0)

    def test_retry_after_longer_than_limit_stops_without_an_early_retry(self):
        self.https.return_value = response(b"Slow down", 429, "Retry-After: 120\n")

        with self.assertRaises(RequestError) as raised:
            self.client.request_json("GET", ISSUE_PATH)

        self.assertEqual(raised.exception.status, 429)
        self.assertEqual(self.https.call_count, 1)
        self.sleep.assert_not_called()

    def test_invalid_retry_after_uses_default_delay(self):
        self.https.side_effect = [
            response(b"Unavailable", 503, "Retry-After: invalid\n"),
            response(),
        ]

        result = self.client.request_json("GET", ISSUE_PATH)

        self.assertEqual(result, {})
        self.sleep.assert_called_once_with(1.0)

    def test_read_stops_after_two_retries(self):
        self.https.side_effect = [
            response(b"Unavailable", 503),
            response(b"Unavailable", 503),
            response(b"Unavailable", 503),
        ]

        with self.assertRaises(RequestError) as raised:
            self.client.request_json("GET", ISSUE_PATH)

        self.assertEqual(raised.exception.status, 503)
        self.assertEqual(self.https.call_count, 3)
        self.assertEqual(self.sleep.call_count, 2)
        self.sleep.assert_called_with(2.0)

    def test_retries_can_be_disabled(self):
        client = JiraClient(BASE_URL, AUTH, max_retries=0)
        self.https.return_value = response(b"Unavailable", 503)

        with self.assertRaises(RequestError):
            client.request_json("GET", ISSUE_PATH)

        self.assertEqual(self.https.call_count, 1)
        self.sleep.assert_not_called()

    def test_authentication_failure_is_not_retried(self):
        self.https.return_value = response(b"Authentication required", 401)

        with self.assertRaises(RequestError) as raised:
            self.client.request_json("GET", ISSUE_PATH)

        self.assertEqual(raised.exception.status, 401)
        self.assertEqual(self.https.call_count, 1)
        self.sleep.assert_not_called()

    def test_permission_failure_is_not_retried(self):
        self.https.return_value = response(b"Permission denied", 403)

        with self.assertRaises(RequestError) as raised:
            self.client.request_json("GET", ISSUE_PATH)

        self.assertEqual(raised.exception.status, 403)
        self.assertEqual(self.https.call_count, 1)
        self.sleep.assert_not_called()

    def test_local_permission_failure_is_not_retried(self):
        self.https.side_effect = urllib.error.URLError(PermissionError("Operation not permitted"))

        with self.assertRaisesRegex(RuntimeError, "Operation not permitted"):
            self.client.request_json("GET", ISSUE_PATH)

        self.assertEqual(self.https.call_count, 1)
        self.sleep.assert_not_called()

    def test_permission_failure_while_reading_an_error_stops_retries(self):
        failed_response = response(b"", 503)
        self.https.return_value = failed_response

        with patch.object(failed_response, "read", side_effect=PermissionError("Denied")):
            with self.assertRaisesRegex(RuntimeError, "No retry was made"):
                self.client.request_json("GET", ISSUE_PATH)

        self.assertEqual(self.https.call_count, 1)
        self.sleep.assert_not_called()

    def test_read_timeout_stops_with_a_clear_error(self):
        self.https.side_effect = TimeoutError("timed out")

        with self.assertRaisesRegex(RuntimeError, "No retry was made"):
            self.client.request_json("GET", ISSUE_PATH)

        self.assertEqual(self.https.call_count, 1)
        self.sleep.assert_not_called()

    def test_uncertain_update_is_not_retried(self):
        self.https.side_effect = urllib.error.URLError(TimeoutError("timed out"))

        with self.assertRaisesRegex(RuntimeError, "write result may be unknown"):
            self.client.request_json("PUT", ISSUE_PATH, {"fields": {}})

        self.assertEqual(self.https.call_count, 1)
        self.sleep.assert_not_called()

    def test_update_service_failure_is_not_retried(self):
        self.https.return_value = response(b"Unavailable", 503)

        with self.assertRaisesRegex(RequestError, "write result may be unknown"):
            self.client.request_json("PUT", ISSUE_PATH, {"fields": {}})

        self.assertEqual(self.https.call_count, 1)
        self.sleep.assert_not_called()

    def test_long_error_body_does_not_hide_uncertain_write_guidance(self):
        self.https.return_value = response(b"x" * 5000, 503)

        with self.assertRaisesRegex(RequestError, "write result may be unknown"):
            self.client.request_json("PUT", ISSUE_PATH, {"fields": {}})

        self.assertEqual(self.https.call_count, 1)
        self.sleep.assert_not_called()

    def test_invalid_update_response_does_not_cause_another_write(self):
        self.https.return_value = response(b"<html>Unexpected response</html>")

        with self.assertRaisesRegex(RuntimeError, "write result may be unknown"):
            self.client.request_json("PUT", ISSUE_PATH, {"fields": {}})

        self.assertEqual(self.https.call_count, 1)
        self.sleep.assert_not_called()

    def test_rate_limited_update_is_not_retried(self):
        self.https.return_value = response(b"Slow down", 429, "Retry-After: 1\n")

        with self.assertRaises(RequestError) as raised:
            self.client.request_json("PUT", ISSUE_PATH, {"fields": {}})

        self.assertEqual(raised.exception.status, 429)
        self.assertEqual(self.https.call_count, 1)
        self.sleep.assert_not_called()

    def test_transition_post_is_not_retried_after_a_server_error(self):
        self.https.return_value = response(b"Unavailable", 503)

        with self.assertRaisesRegex(RequestError, "write result may be unknown"):
            self.client.request_json("POST", ISSUE_PATH + "/transitions",
                                     {"transition": {"id": "31"}})

        self.assertEqual(self.https.call_count, 1)
        self.sleep.assert_not_called()

    def test_create_post_is_not_treated_as_a_read(self):
        self.https.return_value = response(b"Unavailable", 503)

        with self.assertRaises(RequestError):
            self.client.request_json("POST", "/rest/api/3/issue", {"fields": {}})

        self.assertEqual(self.https.call_count, 1)
        self.sleep.assert_not_called()

    def test_http_errors_redact_credentials_and_omit_query_strings(self):
        self.https.return_value = response(
            b"bad token / dXNlcjp0b2tlbg== / Basic dXNlcjp0b2tlbg== / user:token", 400
        )

        with self.assertRaises(RequestError) as raised:
            self.client.request_json("GET", ISSUE_PATH + "?private=query")

        self.assertEqual(raised.exception.url, ISSUE_URL)
        self.assertEqual(
            raised.exception.body,
            "bad [REDACTED] / [REDACTED] / [REDACTED] / [REDACTED]",
        )
        diagnostic = "".join(traceback.format_exception(raised.exception))
        self.assertNotIn("token", diagnostic)
        self.assertNotIn("dXNlcjp0b2tlbg==", diagnostic)
        self.assertNotIn("private=query", diagnostic)

    def test_transport_errors_redact_credentials(self):
        self.https.side_effect = urllib.error.URLError("Failed with token")

        with self.assertRaises(RuntimeError) as raised:
            self.client.request_json("GET", ISSUE_PATH)

        diagnostic = "".join(traceback.format_exception(raised.exception))
        self.assertNotIn("token", diagnostic)
        self.assertIn("[REDACTED]", diagnostic)
        self.assertEqual(self.https.call_count, 1)

    def test_from_env_authenticates_without_printing_credentials(self):
        variables = {
            "ATLASSIAN_URL": BASE_URL,
            "ATLASSIAN_EMAIL": "user",
            "ATLASSIAN_API_TOKEN": "token",
        }
        output = io.StringIO()

        with patch.dict(os.environ, variables), patch("sys.stderr", output):
            client = JiraClient.from_env()
            client.request_json("GET", ISSUE_PATH)

        self.assertEqual(self.https.call_args.args[1].get_header("Authorization"), AUTH)
        self.assertEqual(output.getvalue(), "")

    def test_missing_environment_reports_all_required_names_without_a_request(self):
        output = io.StringIO()

        with patch("sys.stderr", output), self.assertRaises(SystemExit) as raised:
            JiraClient.from_env()

        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(
            output.getvalue(),
            "Missing environment variables: ATLASSIAN_URL, ATLASSIAN_EMAIL, ATLASSIAN_API_TOKEN\n",
        )
        self.https.assert_not_called()

    def test_whitespace_environment_value_is_missing(self):
        variables = {
            "ATLASSIAN_URL": BASE_URL,
            "ATLASSIAN_EMAIL": "user",
            "ATLASSIAN_API_TOKEN": " \t ",
        }
        output = io.StringIO()

        with patch.dict(os.environ, variables), patch("sys.stderr", output):
            with self.assertRaises(SystemExit) as raised:
                JiraClient.from_env()

        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(output.getvalue(), "Missing environment variables: ATLASSIAN_API_TOKEN\n")
        self.https.assert_not_called()


if __name__ == "__main__":
    unittest.main()
