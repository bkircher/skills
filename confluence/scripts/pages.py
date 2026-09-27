"""Confluence page search, reads, and guarded single-page writes."""

import json
import re
import urllib.parse
from typing import Any

from adf import render_markdown
from client import ConfluenceClient, RequestError
from rich_text import from_markdown, from_text, replace_section, validate_document


class ConfluencePages:
    def __init__(self, client: ConfluenceClient) -> None:
        self.client = client

    def page_id(self, target: str) -> str:
        target = target.strip()
        if target.isascii() and target.isdecimal():
            return target
        try:
            parts = urllib.parse.urlsplit(target)
        except ValueError:
            parts = None
        if parts is None or parts.scheme != "https" or parts.netloc.lower() != urllib.parse.urlsplit(self.client.base_url).netloc or parts.fragment or parts.username or parts.password:
            raise ValueError("Supply a page ID or an HTTPS page URL on ATLASSIAN_URL")
        match = re.fullmatch(r"/wiki/spaces/[^/]+/pages/(\d+)(?:/[^/]*)?/?", parts.path)
        query = urllib.parse.parse_qs(parts.query)
        if match and not parts.query:
            return match[1]
        if parts.path == "/wiki/pages/viewpage.action" and set(query) == {"pageId"} and len(query["pageId"]) == 1 and query["pageId"][0].isascii() and query["pageId"][0].isdecimal():
            return query["pageId"][0]
        raise ValueError("Supply a page ID or an HTTPS /wiki/spaces/.../pages/ID page URL")

    def url(self, page_id: str) -> str:
        return f"{self.client.base_url}/wiki/pages/viewpage.action?pageId={page_id}"

    def search(self, query: str, *, space: str | None = None, limit: int = 10) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip() or any(ord(c) < 32 for c in query):
            raise ValueError("Search text must be nonempty and on one line")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Search limit must be from 1 through 100")
        if space is not None and not re.fullmatch(r"[A-Za-z0-9_~-]+", space):
            raise ValueError("Space must be one space key")
        cql = f'type = "page" AND text ~ {json.dumps(query.strip(), ensure_ascii=False)}'
        if space:
            cql += f' AND space = "{space}"'
        path = "/wiki/rest/api/search?" + urllib.parse.urlencode({
            "cql": cql, "expand": "content.space,content.body.atlas_doc_format",
            "limit": min(limit, 25)
        })
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        while path and len(results) < limit:
            if path in seen:
                raise RuntimeError("Confluence search repeated a pagination link")
            seen.add(path)
            data = self.client.request_object("GET", path)
            items = data.get("results", [])
            if not isinstance(items, list):
                raise RuntimeError("Confluence search returned invalid results")
            for item in items:
                if len(results) == limit:
                    break
                content = item.get("content") or {}
                page_id = str(content.get("id") or "")
                if not page_id.isascii() or not page_id.isdecimal():
                    continue
                doc = _adf(content)
                results.append({
                    "id": page_id, "title": content.get("title") or item.get("title"),
                    "space_key": (content.get("space") or {}).get("key"),
                    "url": self.url(page_id), "excerpt": item.get("excerpt") or "",
                    "last_modified": item.get("lastModified") or
                    (content.get("history") or {}).get("lastUpdated", {}).get("when"),
                    "body_markdown": render_markdown(doc) if doc else "",
                })
            next_link = (data.get("_links") or {}).get("next")
            path = self._next(next_link) if next_link else ""
        return {"results": results, "has_more": bool(path)}

    def get(self, target: str, *, children: bool = False, raw_adf: bool = False,
            for_update: bool = False) -> dict[str, Any]:
        page_id = self.page_id(target)
        page = self._read(page_id)
        result = self._format(page)
        if raw_adf:
            result["body_adf"] = _adf(page)
        if for_update:
            result["snapshot"] = self._snapshot(page)
        if children:
            path = f"/wiki/api/v2/pages/{page_id}/children?limit=100"
            result["children"] = []
            seen: set[str] = set()
            while path:
                if path in seen:
                    raise RuntimeError("Confluence children repeated a pagination link")
                seen.add(path)
                data = self.client.request_object("GET", path)
                for child in data.get("results", []):
                    child_id = str(child.get("id") or "")
                    if child_id.isascii() and child_id.isdecimal():
                        result["children"].append({"id": child_id, "title": child.get("title"),
                                                   "url": self.url(child_id)})
                next_link = (data.get("_links") or {}).get("next")
                path = self._next(next_link) if next_link else ""
        return result

    def create(self, spec: dict[str, Any], *, preview: bool = False) -> dict[str, Any]:
        _keys(spec, {"space_id", "title", "parent_id", "body"}, {"space_id", "title", "body"})
        space_id = _id(spec["space_id"], "space_id")
        title = _title(spec["title"])
        parent_id = _id(spec["parent_id"], "parent_id") if "parent_id" in spec else None
        doc = _content(spec["body"])
        payload: dict[str, Any] = {"spaceId": space_id, "status": "current", "title": title,
                                   "body": _body(doc)}
        if parent_id:
            payload["parentId"] = parent_id
        result = {"status": "preview" if preview else "unknown", "space_id": space_id,
                  "title": title, "parent_id": parent_id, "body_markdown": render_markdown(doc)}
        if preview:
            return result
        try:
            saved = self.client.request_object("POST", "/wiki/api/v2/pages", payload)
        except (RuntimeError, OSError) as error:
            return self._write_error(result, error)
        new_id = str(saved.get("id") or "")
        if not new_id.isascii() or not new_id.isdecimal():
            return {**result, "status": "unverified", "verified": False,
                    "message": "Confluence accepted the write but did not return a page ID. Do not repeat the create."}
        result.update({"id": new_id, "url": self.url(new_id)})
        return self._verify(result, new_id, title, doc, space_id=space_id, parent_id=parent_id)

    def update(self, target: str, spec: dict[str, Any], *, preview: bool = False) -> dict[str, Any]:
        _keys(spec, {"expected", "title", "body", "section"}, set())
        if not any(key in spec for key in ("title", "body", "section")) or ("body" in spec and "section" in spec):
            raise ValueError("Update needs title, body, or section; body and section cannot be combined")
        title = _title(spec["title"]) if "title" in spec else None
        body = _content(spec["body"]) if "body" in spec else None
        section = spec.get("section")
        if "section" in spec:
            _keys(section, {"heading", "content", "create", "level"}, {"heading", "content"})
            if not isinstance(section["heading"], str) or not section["heading"].strip():
                raise ValueError("Section heading is required")
            section_doc = _content(section["content"])
        page_id = self.page_id(target)
        if not preview:
            self._check_expected(spec.get("expected"), page_id)
        page = self._read(page_id)
        if page.get("status") != "current":
            raise ValueError("Only published pages can be updated")
        snapshot = self._snapshot(page)
        if not preview and spec["expected"] != snapshot:
            return {"status": "conflict", "id": page_id, "url": self.url(page_id),
                    "verified": False, "message": "Page version changed. Read it again before editing."}
        original = _adf(page)
        if original is None:
            raise ValueError("This page has no valid ADF body. A safe update is not supported")
        if section is not None:
            body = replace_section(original, section["heading"], section_doc,
                                   create=section.get("create", False), level=section.get("level", 2))
        if body is None:
            body = original
        new_title = title if title is not None else page.get("title")
        _title(new_title)
        result = {"status": "preview" if preview else "unknown", "id": page_id,
                  "url": self.url(page_id), "title": new_title, "snapshot": snapshot,
                  "changed_fields": [key for key in ("title", "body", "section") if key in spec],
                  "body_markdown": render_markdown(body)}
        if preview:
            return result
        payload = {"id": page_id, "status": "current", "title": new_title,
                   "body": _body(body), "version": {"number": snapshot["version"] + 1}}
        try:
            self.client.request_object("PUT", f"/wiki/api/v2/pages/{page_id}", payload)
        except (RuntimeError, OSError) as error:
            return self._write_error(result, error)
        return self._verify(result, page_id, new_title, body,
                            version=snapshot["version"] + 1)

    def _read(self, page_id: str) -> dict[str, Any]:
        return self.client.request_object(
            "GET", f"/wiki/api/v2/pages/{page_id}?body-format=atlas_doc_format&include-labels=true")

    def _format(self, page: dict[str, Any]) -> dict[str, Any]:
        doc = _adf(page)
        page_id = str(page.get("id") or "")
        labels = page.get("labels") or {}
        return {"id": page_id, "title": page.get("title"), "space_id": page.get("spaceId"),
                "parent_id": page.get("parentId"), "status": page.get("status"),
                "url": self.url(page_id), "body_markdown": render_markdown(doc) if doc else "",
                "body_available": doc is not None,
                "labels": [label.get("name") for label in labels.get("results", []) if label.get("name")],
                "labels_have_more": bool((labels.get("meta") or {}).get("hasMore")),
                "version": (page.get("version") or {}).get("number"),
                "created_at": page.get("createdAt"),
                "updated_at": (page.get("version") or {}).get("createdAt")}

    def _snapshot(self, page: dict[str, Any]) -> dict[str, Any]:
        page_id = str(page.get("id") or "")
        version = (page.get("version") or {}).get("number")
        if not page_id.isascii() or not page_id.isdecimal() or type(version) is not int or version < 1:
            raise ValueError("Page ID or version is unavailable; cannot safely update")
        return {"site": self.client.base_url, "page_id": page_id, "version": version}

    def _check_expected(self, expected: Any, page_id: str) -> None:
        if (not isinstance(expected, dict) or set(expected) != {"site", "page_id", "version"}
                or expected.get("site") != self.client.base_url or expected.get("page_id") != page_id
                or type(expected.get("version")) is not int or expected["version"] < 1):
            raise ValueError("expected must be the snapshot for this site and page from get --for-update or preview")

    def _verify(self, result: dict[str, Any], page_id: str, title: str,
                doc: dict[str, Any], *, space_id: str | None = None,
                parent_id: str | None = None, version: int | None = None) -> dict[str, Any]:
        try:
            page = self._read(page_id)
        except (RuntimeError, OSError) as error:
            return {**result, "status": "unverified", "verified": False,
                    "message": f"The write was accepted, but the read-back failed: {error}"}
        matches = (str(page.get("id")) == page_id and page.get("title") == title
                   and page.get("status") == "current" and _adf(page) == doc)
        if version is not None:
            matches = matches and (page.get("version") or {}).get("number") == version
        if space_id is not None:
            matches = matches and str(page.get("spaceId")) == space_id
        if parent_id is not None:
            matches = matches and str(page.get("parentId")) == parent_id
        return {**result, "status": "updated" if version is not None and matches else
                "created" if matches else "unverified", "verified": bool(matches),
                "message": None if matches else "Read-back did not match. Inspect the page before another write."}

    def _write_error(self, result: dict[str, Any], error: Exception) -> dict[str, Any]:
        if isinstance(error, RequestError) and error.status == 409 and "id" in result:
            status = "conflict"
        elif isinstance(error, RequestError) and error.status in {400, 401, 403, 404, 409, 413, 429}:
            status = "rejected"
        else:
            status = "unknown"
        return {**result, "status": status, "verified": False, "message": str(error)}

    def _next(self, link: str) -> str:
        # Search v1 links can start with /rest; v2 links can start with /wiki/api.
        if not isinstance(link, str) or not link:
            raise ValueError("Invalid Confluence pagination link")
        if link.startswith("/rest/"):
            link = "/wiki" + link
        parsed = urllib.parse.urlsplit(urllib.parse.urljoin(self.client.base_url, link))
        site = urllib.parse.urlsplit(self.client.base_url)
        if parsed.scheme != "https" or parsed.netloc != site.netloc or not parsed.path.startswith("/wiki/") or parsed.fragment:
            raise ValueError("Confluence returned an unsafe pagination link")
        return urllib.parse.urlunsplit(("", "", parsed.path, parsed.query, ""))


def _id(value: Any, name: str) -> str:
    if (isinstance(value, bool) or not isinstance(value, (str, int))
            or not str(value).isascii() or not str(value).isdecimal()
            or str(value).startswith("0")):
        raise ValueError(f"{name} must be a positive numeric ID without leading zeros")
    return str(value)


def _title(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or any(ord(char) < 32 for char in value):
        raise ValueError("Title must be nonempty and on one line")
    return value


def _keys(spec: Any, allowed: set[str], required: set[str]) -> None:
    if not isinstance(spec, dict) or set(spec) - allowed or required - set(spec):
        raise ValueError(f"Expected one object with {', '.join(sorted(required))}; allowed: {', '.join(sorted(allowed))}")


def _content(value: Any) -> dict[str, Any]:
    _keys(value, {"text", "markdown", "adf"}, set())
    if len(value) != 1:
        raise ValueError("Content must contain exactly one of text, markdown, or adf")
    if "text" in value:
        return from_text(value["text"])
    if "markdown" in value:
        return from_markdown(value["markdown"])
    return validate_document(value["adf"])


def _adf(page: dict[str, Any]) -> dict[str, Any] | None:
    value = ((page.get("body") or {}).get("atlas_doc_format") or {}).get("value")
    if not value:
        return None
    try:
        return validate_document(json.loads(value) if isinstance(value, str) else value)
    except (ValueError, TypeError):
        return None


def _body(doc: dict[str, Any]) -> dict[str, str]:
    return {"representation": "atlas_doc_format", "value": json.dumps(doc, ensure_ascii=False)}
