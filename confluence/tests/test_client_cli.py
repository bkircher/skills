"""CLI input and client safety behavior without network access."""

import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from client import ConfluenceClient, RequestError  # noqa: E402
from confluence import main  # noqa: E402


class FakeOpener:
    def __init__(self, error):
        self.error = error
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request.get_method(), request.full_url))
        raise self.error


class ClientTests(unittest.TestCase):
    def test_invalid_site_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTPS site URL"):
            ConfluenceClient("https://example.atlassian.net/wiki", "Basic secret")

    def test_create_is_not_retried_after_http_503(self):
        opener = FakeOpener(urllib.error.HTTPError(
            "https://example.atlassian.net/wiki/api/v2/pages", 503, "Unavailable", {}, io.BytesIO(b"busy")))
        with patch("urllib.request.build_opener", return_value=opener):
            client = ConfluenceClient("https://example.atlassian.net", "Basic secret")

        with self.assertRaises(RequestError):
            client.request_object("POST", "/wiki/api/v2/pages", {"title": "New"})

        self.assertEqual(len(opener.calls), 1)

    def test_redirect_is_refused_and_credentials_are_not_sent_to_other_site(self):
        opener = FakeOpener(urllib.error.HTTPError(
            "https://example.atlassian.net/wiki/api/v2/pages/123", 302, "Moved",
            {"Location": "https://other.atlassian.net/wiki/api/v2/pages/123"}, io.BytesIO(b"")))
        with patch("urllib.request.build_opener", return_value=opener):
            client = ConfluenceClient("https://example.atlassian.net", "Basic secret")

        with self.assertRaisesRegex(RequestError, "Redirect refused"):
            client.request_object("GET", "/wiki/api/v2/pages/123")

        self.assertEqual(len(opener.calls), 1)


class CLITests(unittest.TestCase):
    def test_duplicate_keys_fail_before_credential_check(self):
        with patch("sys.stdin", io.StringIO('{"title":"A","title":"B"}')):
            with patch.dict("os.environ", {}, clear=True):
                with patch("sys.stderr", new_callable=io.StringIO) as stderr:
                    result = main(["create", "--input", "-"])

        self.assertEqual(result, 2)
        self.assertEqual(json.loads(stderr.getvalue())["message"], "Input JSON contains a duplicate key")

    def test_missing_credentials_does_not_log_values(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("sys.stderr", new_callable=io.StringIO) as stderr:
                with self.assertRaises(SystemExit) as raised:
                    main(["get", "123"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("ATLASSIAN_API_TOKEN", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
