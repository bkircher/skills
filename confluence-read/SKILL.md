---
name: confluence-read
description: Search Confluence pages and fetch page content. Use when a user wants to find or read Confluence wiki pages, or when context from Confluence is needed.
---

# Confluence data access instructions

Search and fetch Confluence Cloud pages, returning content as Markdown.

## Inputs

- Search query text, or a Confluence page URL / page ID
- Environment variables: `ATLASSIAN_URL`, `ATLASSIAN_EMAIL`, `ATLASSIAN_API_TOKEN`

## Workflow

### 1) Verify environment variables

Ensure all required variables are set. Never output or log token values.
If missing, ask the user to set them before calling the API.

Variables: `ATLASSIAN_URL`, `ATLASSIAN_EMAIL`, `ATLASSIAN_API_TOKEN`

### 2) Identify the intent

- **Search**: the user wants to find pages by keyword, optionally within a space.
- **Fetch**: the user provides a specific page ID or URL and wants its content.

### 3) Run the appropriate script

#### Search pages

```
python scripts/search.py <QUERY> [--space SPACEKEY] [--limit N]
```

Returns a JSON array of matching pages with title, URL, excerpt, and rendered
Markdown body. Default limit is 10.

#### Fetch a single page

```
python scripts/fetch_page.py <PAGE_ID_OR_URL> [--children]
```

Accepts a numeric page ID or a full Confluence page URL. Returns JSON with the
page title, labels, rendered Markdown body, and metadata.

Pass `--children` to include a list of child pages (title and URL only).

### 4) Present results

- Use the `body_markdown` field to show page content.
- Summarize or quote as appropriate for the user's request.

## Notes

- Read-only operation: do not alter page data unless explicitly authorized.
- Never log or output secrets -- reference environment variable names only.
- ADF rendering is handled by the shared `jira.py` renderer.
