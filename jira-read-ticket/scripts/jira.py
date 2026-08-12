"""Jira API client and issue helpers."""

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Self


ISSUE_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


class RequestError(RuntimeError):
    def __init__(self, status: int, url: str, body: str) -> None:
        super().__init__(f"HTTP {status} for {url}\n{body}")
        self.status = status
        self.url = url
        self.body = body


class JiraClient:
    def __init__(self, base_url: str, auth_header: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._auth_header = auth_header

    @classmethod
    def from_env(cls) -> Self:
        return cls(_require_env("ATLASSIAN_URL"), _load_auth())

    def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        url = self._url(path)
        data: bytes | None = None
        headers = {
            "Accept": "application/json",
            "Authorization": self._auth_header,
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RequestError(e.code, url, err_body) from e

        try:
            result = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Failed to parse JSON from {url}: {e}\nRaw:\n{raw}"
            ) from e

        if not isinstance(result, (dict, list)):
            raise RuntimeError(f"Expected a JSON object or array from {url}")
        return result

    def request_object(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.request_json(method, path, payload)
        if not isinstance(result, dict):
            raise RuntimeError(f"Expected a JSON object from {self._url(path)}")
        return result

    def request_array(self, method: str, path: str) -> list[Any]:
        result = self.request_json(method, path)
        if not isinstance(result, list):
            raise RuntimeError(f"Expected a JSON array from {self._url(path)}")
        return result

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"


def extract_issue_key(value: str) -> str:
    match = ISSUE_KEY_RE.search(value)
    if not match:
        raise ValueError(f"Could not find a Jira issue key in: {value}")
    return match.group(1)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"Missing environment variable: {name}", file=sys.stderr)
        raise SystemExit(2)
    return value


def _load_auth() -> str:
    email = _require_env("ATLASSIAN_EMAIL")
    token = _require_env("ATLASSIAN_API_TOKEN")
    creds = f"{email}:{token}".encode("utf-8")
    return "Basic " + base64.b64encode(creds).decode("utf-8")
