"""Confluence Cloud API client with safe transport and diagnostics."""

import base64
import binascii
import http.client
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from typing import Any, Self


RETRY_STATUSES = {429, 502, 503, 504}
MAX_RETRY_DELAY = 30.0
ENV_NAMES = ("ATLASSIAN_URL", "ATLASSIAN_EMAIL", "ATLASSIAN_API_TOKEN")


class RequestError(RuntimeError):
    def __init__(self, status: int, url: str, body: str) -> None:
        super().__init__(f"HTTP {status} for {url}\n{body}")
        self.status = status
        self.url = url
        self.body = body


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        # Do not forward credentials or change the request method on a redirect.
        return None


class ConfluenceClient:
    def __init__(
        self,
        base_url: str,
        auth_header: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self.base_url = _normalize_base_url(base_url)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive, finite number")
        if not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
        if not auth_header or "\r" in auth_header or "\n" in auth_header:
            raise ValueError("An authentication header without line breaks is required")
        self._auth_header = auth_header
        self._timeout = timeout
        self._max_retries = max_retries
        self._opener = urllib.request.build_opener(_NoRedirects())
        self._secrets = _auth_secrets(auth_header)

    @classmethod
    def from_env(cls) -> Self:
        values = {name: os.getenv(name, "").strip() for name in ENV_NAMES}
        missing = [name for name, value in values.items() if not value]
        if missing:
            print("Missing environment variables: " + ", ".join(missing), file=sys.stderr)
            raise SystemExit(2)
        credentials = f"{values['ATLASSIAN_EMAIL']}:{values['ATLASSIAN_API_TOKEN']}"
        auth = "Basic " + base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        return cls(values["ATLASSIAN_URL"], auth)

    def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any] | None:
        """Send a request. Return None for an empty successful response.

        Retry only selected HTTP errors on known read operations. Redirects,
        transport errors, permission failures, and writes are not retried.
        """
        url = self._url(path)
        display_url = self._display_url(url)
        method = method.upper()
        safe_read = method in {"GET", "HEAD"}
        write_note = (
            ""
            if safe_read
            else "\nThe write result may be unknown. Read the page before another write."
        )
        data: bytes | None = None
        headers = {
            "Accept": "application/json",
            "Authorization": self._auth_header,
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        for attempt in range(self._max_retries + 1):
            try:
                with self._opener.open(req, timeout=self._timeout) as resp:
                    raw = resp.read()
                break
            except urllib.error.HTTPError as error:
                try:
                    with error:
                        body = error.read().decode("utf-8", errors="replace")
                except (OSError, urllib.error.URLError, http.client.HTTPException):
                    raise RuntimeError(
                        f"Could not read the HTTP {error.code} response from {display_url}."
                        f" No retry was made.{write_note}"
                    ) from None

                if 300 <= error.code < 400:
                    body = self._redirect_message(url, error.headers.get("Location", ""))
                elif safe_read and error.code in RETRY_STATUSES:
                    delay = _retry_delay(error.headers.get("Retry-After"), attempt)
                    if attempt < self._max_retries and delay is not None:
                        time.sleep(delay)
                        continue

                body = self._redact(body)[:4000] or "Confluence returned no error details."
                if error.code >= 500:
                    body += write_note
                raise RequestError(error.code, display_url, body) from None
            except (OSError, urllib.error.URLError, http.client.HTTPException) as error:
                reason = (
                    error.reason if isinstance(error, urllib.error.URLError) else error
                )
                detail = self._redact(str(reason))[:1000]
                raise RuntimeError(
                    f"Confluence connection failed for {display_url}: {detail}."
                    f" No retry was made.{write_note}"
                ) from None

        if not raw:
            return None
        try:
            result = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Do not include response bodies or chained errors in diagnostics.
            raise RuntimeError(
                f"Confluence returned invalid JSON from {display_url}.{write_note}"
            ) from None

        if not isinstance(result, (dict, list)):
            raise RuntimeError(
                f"Expected a JSON object or array from {display_url}.{write_note}"
            )
        return result

    def request_object(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.request_json(method, path, payload)
        if not isinstance(result, dict):
            raise RuntimeError(
                f"Expected a JSON object from {self._display_url(self._url(path))}"
            )
        return result

    def request_array(self, method: str, path: str) -> list[Any]:
        result = self.request_json(method, path)
        if not isinstance(result, list):
            raise RuntimeError(
                f"Expected a JSON array from {self._display_url(self._url(path))}"
            )
        return result

    def _url(self, path: str) -> str:
        invalid = ValueError("Use a relative API path without a fragment or whitespace")
        if _has_unsafe_url_characters(path):
            raise invalid
        try:
            parts = urllib.parse.urlsplit(path)
        except ValueError:
            raise invalid from None
        if parts.scheme or parts.netloc or parts.fragment or path.startswith("//"):
            raise invalid
        return f"{self.base_url}/{path.lstrip('/')}"

    def _redact(self, value: str) -> str:
        for secret in self._secrets:
            value = value.replace(secret, "[REDACTED]")
        return value

    def _display_url(self, url: str) -> str:
        # Query strings can contain confidential search terms or credentials.
        return self._redact(url.split("?", 1)[0])

    def _redirect_message(self, url: str, location: str) -> str:
        message = "Redirect refused. No redirect was followed."
        try:
            target = urllib.parse.urlsplit(urllib.parse.urljoin(url, location))
            origin = _normalize_base_url(
                urllib.parse.urlunsplit((target.scheme, target.netloc, "", "", ""))
            )
        except ValueError:
            return message + " Check ATLASSIAN_URL. Use the canonical HTTPS site URL."
        return (
            f"{message} Verify the proposed site {origin} before setting ATLASSIAN_URL."
            " The configured URL must be the canonical HTTPS site URL."
        )


def _has_unsafe_url_characters(value: str) -> bool:
    return "\\" in value or any(
        char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value
    )


def _normalize_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    message = (
        "ATLASSIAN_URL must be an HTTPS site URL, such as https://example.atlassian.net."
        " Do not include credentials, a path, a query, or a fragment."
    )
    if _has_unsafe_url_characters(value):
        raise ValueError(message)
    try:
        parts = urllib.parse.urlsplit(value)
        port = parts.port
    except ValueError:
        raise ValueError(message) from None
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.path
        or parts.query
        or parts.fragment
        or port == 0
    ):
        raise ValueError(message)
    return urllib.parse.urlunsplit(("https", parts.netloc.lower(), "", "", ""))


def _auth_secrets(auth_header: str) -> list[str]:
    scheme, _, credentials = auth_header.partition(" ")
    secrets = [auth_header, credentials]
    if scheme.lower() == "basic":
        try:
            decoded = base64.b64decode(credentials, validate=True).decode("utf-8")
            secrets.extend((decoded, decoded.partition(":")[2]))
        except (binascii.Error, UnicodeDecodeError):
            pass
    return sorted((secret for secret in secrets if secret), key=len, reverse=True)


def _retry_delay(retry_after: str | None, attempt: int) -> float | None:
    delay = min(2.0 ** min(attempt, 5), MAX_RETRY_DELAY)
    if retry_after:
        value = retry_after.strip()
        if value.isascii() and value.isdecimal():
            try:
                delay = float(value)
            except ValueError:
                return None
        else:
            try:
                date = parsedate_to_datetime(value)
                if date.tzinfo is not None:
                    delay = max(0.0, date.timestamp() - time.time())
            except (ValueError, OverflowError):
                pass
    # Do not retry before the server's requested time or wait without a limit.
    return delay if math.isfinite(delay) and delay <= MAX_RETRY_DELAY else None
