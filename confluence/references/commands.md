# Confluence commands and input

Run `python3 scripts/confluence.py --help` from the skill directory or use the
absolute script path. Python 3.14+ standard library only. All commands require
`ATLASSIAN_URL`, `ATLASSIAN_EMAIL`, and `ATLASSIAN_API_TOKEN`. The site URL must
be the canonical HTTPS origin, without `/wiki`, a query, or credentials.

## Read and search

- `search QUERY [--space KEY] [--limit N]` searches pages with CQL, default
  limit 10, maximum 100. Returns `results` and `has_more`. Each result can include
  `body_markdown`, an excerpt, title, and numeric ID. Search text is data, not CQL.
- `get ID_OR_URL [--children] [--raw-adf] [--for-update]` returns page metadata,
  labels, and `body_markdown`. `--children` lists all direct children.
  `--raw-adf` returns the original ADF JSON. `--for-update` returns a `snapshot`.
  `body_available: false` means ADF is missing or invalid, not that the page is
  empty. `labels_have_more: true` means the label list is incomplete.

Page targets can be numeric IDs, same-site `/wiki/spaces/KEY/pages/ID/...`
URLs, or same-site `/wiki/pages/viewpage.action?pageId=ID` URLs.

## Create

`create --input FILE [--preview]` creates a **published** page. `--preview`
validates and shows the planned page without writing. Example input:

```json
{
  "space_id": "1234",
  "parent_id": "5678",
  "title": "Operations guide",
  "body": {"markdown": "# Overview\n\nInstructions here."}
}
```

`parent_id` is optional; omit it for a root page. Use a numeric `space_id`
from a page already in the correct space. A create may not be safely repeated
if its result is unknown.

## Update

`update ID_OR_URL --input FILE [--preview]` updates one **published** page. A
preview reads the page and returns a `snapshot` without writing. Apply requires
`expected` equal to the complete snapshot from `get --for-update` or preview.
The CLI checks the page version before writing, and Confluence checks the
incremented version. Example title and section update:

```json
{
  "expected": {"site": "https://example.atlassian.net", "page_id": "123456", "version": 3},
  "title": "Operations guide",
  "section": {
    "heading": "Overview",
    "content": {"markdown": "New guidance with **bold** text."}
  }
}
```

`section.create: true` can add a missing section; `section.level` defaults to
2. It fails when multiple headings match. A section edit preserves untouched
ADF nodes, including macros and tables. The alternative `body` replaces the
*whole* page body; do not use it for partial edits. A title-only update sends
back the original ADF body because the API requires a body for page updates.
Updates can reconcile or replace an existing unpublished draft on the server.
Do not use this command if draft content must remain untouched.

For `body` and `section.content`, use exactly one of:

- `{"text": "Literal plain text"}`: one paragraph with line breaks.
- `{"markdown": "# Heading\n\n- Item"}`: limited Markdown. Supported:
  headings, paragraphs, flat lists, code fences, bold, italic, inline code,
  and links. Unsupported constructs are rejected; this is *not* a general
  Markdown parser.
- `{"adf": {"type": "doc", "version": 1, "content": [...]}}`:
  ADF for richer content. Validate changes to raw ADF before submitting.

Do not convert `body_markdown` back to ADF to preserve existing content.

## Results and failures

A successful write has `status: created` or `updated` and `verified: true`.
`rejected` means the server declined the write; `conflict` means the page version
changed before the write. `unknown` means a write might have happened, and
`unverified` means the write was accepted but the read-back failed or differed.
For `unknown` or `unverified`, inspect the page before doing more work; never
repeat a create automatically. Do not claim a write was verified unless the
result reports `verified: true`.
