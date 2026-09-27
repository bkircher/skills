# Jira commands and input

Run `python3 scripts/jira.py <command>` with the script path resolved against the
skill directory. All commands use Jira Cloud REST API v3 and the shared client.
No command supports bulk writes, deletion, or arbitrary HTTP requests.

## Search

```sh
python3 scripts/jira.py search --text "login failure" --project ABC
python3 scripts/jira.py search --assignee me --open --limit 50
python3 scripts/jira.py search --jql 'project = ABC ORDER BY updated DESC' --fields summary,status
```

Use either `--jql` or filters. Filters include `--text`, `--project`, `--assignee`
(`me` or an account ID), and `--open`. Open issues are selected by status category,
not by a list of English status names. There is no implicit search of the whole site.

The default limit is 20. Limits must be from 1 through 1000. The script fetches
pages internally until it reaches the limit or the last page. Results contain
`count`, `truncated`, and `next_page_token`. To continue, use the same query and
field selection with `--page-token <returned-token>`.

## Read

```sh
python3 scripts/jira.py get ABC-123
python3 scripts/jira.py get https://example.atlassian.net/browse/ABC-123 --comments
python3 scripts/jira.py get ABC-123 --fields summary,description,labels,customfield_10010 --for-update
python3 scripts/jira.py get ABC-123 --acceptance-field customfield_10010 --comments
python3 scripts/jira.py get ABC-123 --comments-only --comment-limit 100
```

Only one key or browse URL is accepted. A supplied issue URL must belong to the
configured site. A key returned by Jira can differ if the issue moved; use the
returned key for subsequent operations.

Default fields: summary, description, labels, status, issue type, project,
priority, assignee, reporter, parent, creation time, and update time. `--fields`
replaces that selection with explicit Jira field IDs. Wildcards are not accepted.
Other fields remain available through their IDs. Use `metadata --fields` to find them.

Results include:

- `key`, `url`, and `fields`.
- `rich_text_fields`: fields rendered from ADF to Markdown in `fields`.
- `missing_fields`: requested fields omitted by Jira. Missing does not mean empty.
- `raw_adf`: original documents, only with `--raw-adf`. Markdown rendering can lose
  unsupported details; do not use it as a lossless editing format.
- `snapshot`: only with `--for-update`. It binds hashes of the returned raw field
  values to this site and issue. Copy it into an update input's `expected` property.

### Acceptance criteria

A description section named `Acceptance criteria` is reported when description
is selected. Its existing heading and formatting are not changed.

`--acceptance-criteria` also discovers custom fields with the exact display name
`Acceptance criteria`, ignoring case. All exact matches are kept separate. No
approximate name match is selected. The field catalog is fetched only on demand.

`--acceptance-field customfield_10010` reads a known field without discovery.
Both plain-text and ADF custom fields are supported. The result identifies each
source field and whether custom fields were checked. Missing custom fields are
reported separately. Never assume one custom-field ID applies to every project.

### Comments

`--comments` adds comments to the issue read. `--comments-only` avoids the
issue-fields request. The latter cannot be combined with field or snapshot options.

Comments have an independent `--comment-limit` (default 20, maximum 1000).
Pagination is internal. The response includes `total`, `truncated`, and
`next_start_at`. Continue with `--comment-start <returned-offset>` when needed.
`--raw-adf` also includes the original comment bodies. Comment writes are not supported.

Other explicitly selected Jira fields can contain their own paginated structures,
such as worklogs. These remain raw Jira metadata; inspect their pagination fields.

## Metadata

```sh
python3 scripts/jira.py metadata --fields
python3 scripts/jira.py metadata --project ABC
python3 scripts/jira.py metadata --project ABC --issue-type Task
python3 scripts/jira.py metadata --project ABC --issue-type 10001
python3 scripts/jira.py metadata --issue ABC-123
```

These commands return field IDs, issue types, required fields, schemas, supported
operations, defaults, and allowed values, where Jira supplies them.

Issue type names must match exactly, ignoring case, and must be unambiguous.
A numeric issue type ID avoids the type-name lookup. Create field metadata is
scoped to project and issue type. Edit metadata is scoped to the issue.

The cache belongs to one client and one command invocation. No credentials,
permissions, or field metadata are written to a disk cache. Normal reads do not
fetch create or edit metadata. Update preflight reads include `expand=editmeta`
in the same issue request.

## Update

1. Read the affected fields with `get --for-update`, or request a preview.
2. Prepare one JSON change object. Copy the returned `snapshot` into `expected`.
3. Run `update`. Do not build a separate HTTP payload or perform manual verification.

```sh
python3 scripts/jira.py update ABC-123 --input changes.json --preview
python3 scripts/jira.py update ABC-123 --input changes.json
```

`--input -` reads JSON from stdin. A preview requires no `expected` snapshot, but
checks one if supplied. It returns a diff and a fresh snapshot without writing.
An applied update requires `expected` and rejects stale or incomplete snapshots.

Example change object, before inserting the actual snapshot:

```json
{
  "fields": {"summary": "Make login error messages clear"},
  "labels": {"add": ["usability"], "remove": ["needs-triage"]},
  "sections": [
    {
      "field": "description",
      "heading": "Acceptance criteria",
      "content": {"markdown": "- Show a clear error for invalid credentials.\n- Keep the entered user name."}
    }
  ]
}
```

For this example, the snapshot must include `summary`, `labels`, and `description`.
Add it as `"expected": {"site": ..., "issue": ..., "hashes": ...}` using the
actual object returned by the script. Do not invent or manually calculate hashes.

Supported input properties:

| Property | Meaning |
| --- | --- |
| `fields` | Explicit Jira field values, including custom-field IDs |
| `text` | New text for whole fields, using the content formats below |
| `sections` | Replace selected rich-text section bodies without rewriting other nodes |
| `labels` | Add/remove named labels without replacing unrelated labels |
| `expected` | Source snapshot for every affected field |

Use `null` in `fields` only when the user requests clearing an optional field.
An empty or missing property does not implicitly clear a field. Omitted fields
are never written. Unknown input properties and conflicting operations are rejected.

For a plain-text custom criteria field, use:

```json
{"fields": {"customfield_10010": "The user can sign in with valid credentials."}}
```

For a whole rich-text field replacement, use:

```json
{"text": {"description": {"markdown": "## Description\n\nNew content."}}}
```

These examples also need an actual `expected` snapshot when applied. Use whole
field replacement only when it is intended. For a partial edit, use `sections`.
A section match ignores case but must be unique. Its original heading node and
all other nodes are preserved, including media, cards, marks, and attributes.
The section body includes subordinate headings up to the next heading of equal
or lower level. Replacement headings must remain below the section level.

A missing section is an error unless its change contains `"create": true`.
A new section is appended, with heading level 2 unless `level` is supplied.
Do not combine whole-field replacement and section edits for the same field.

### Content formats

A content object contains exactly one of:

- `{"text": "literal text"}`: builds a plain ADF paragraph for rich-text fields;
  retains line breaks. For a plain string custom field, sends a string.
- `{"markdown": "..."}`: generates ADF for a supported rich-text field.
- `{"adf": {"type": "doc", "version": 1, "content": [...]}}`: explicit raw ADF.

The supported Markdown subset has paragraphs, `#` headings, flat bullet or
numbered lists, triple-backtick code blocks, `**bold**`, `*italic*`, inline code,
and `[text](https://url)` links. Underscores are literal. Escape literal markers
with a backslash or use `text`. Avoid nested inline marks. Tables, nested lists,
HTML, images, task lists, and blockquotes require raw ADF; do not flatten them.
Use raw ADF for unsupported rich content. Basic ADF structure is checked locally;
Jira performs full schema validation.

The script uses field metadata to distinguish ADF textarea fields from plain
string fields. It does not send Markdown directly to an ADF field.

### Update sequence

The command reads current values and edit metadata, checks the snapshot, builds
one payload, skips unchanged values, writes once, and reads back changed fields.
Label changes use Jira add/remove operations. It does not replace other labels.

Snapshot checks are best effort, not atomic compare-and-swap. Another user can
still edit after the check. Verification reports a mismatch rather than silently
repeating the write. Freshness checks apply to affected fields, not unrelated changes.

## Create

```sh
python3 scripts/jira.py create --input ticket.json --preview
python3 scripts/jira.py create --input ticket.json
```

Example input:

```json
{
  "project": "ABC",
  "issue_type": "Task",
  "fields": {
    "summary": "Improve login error messages",
    "labels": ["usability"]
  },
  "text": {
    "description": {
      "markdown": "## Description\n\nExplain why login failed.\n\n## Acceptance criteria\n\n- Show a clear error.\n- Keep the entered user name."
    }
  }
}
```

Creation requires a project key or ID, an issue type name or ID, and a non-empty
`fields.summary`. Supply other required fields identified by create metadata.
Metadata defaults need not be repeated. Use explicit account IDs, option IDs,
and other identifiers from metadata for reference fields. For example,
`"assignee": {"accountId": "..."}` or `"priority": {"id": "..."}`.

Creation accepts `fields`, `text`, and `sections` as for updates, but no snapshot
or label add/remove operations. Use `fields.labels` for a new issue. A section
on a new document requires `create: true`.

The command resolves metadata, validates fields, creates once, and verifies the
returned issue. A timeout or a response without an issue key leaves the outcome
unknown. Never repeat creation automatically. Check Jira before another create.

## Results and errors

Results are JSON on stdout. Local validation and read errors use stderr. Missing
environment variables are reported by the client before any request. No traceback
is needed for normal failures.

| Status | Meaning | Exit code |
| --- | --- | --- |
| `preview` | No write sent | 0 |
| `unchanged` | Current values already match; no write sent | 0 |
| `updated`, `created` | Write accepted and saved fields verified | 0 |
| `conflict` | Source changed; no write sent | 1 |
| `rejected` | Jira rejected the write; no retry made | 1 |
| `unknown` | Write outcome is uncertain; no retry made | 3 |
| `unverified` | Write accepted, but read-back failed or differs | 3 |

Successful reads and searches exit with 0. Local validation failures exit with 2;
read or connection failures exit with 1. Argument errors also exit with 2.

Do not treat exit code 3 as permission to retry. Always report the known issue
URL, the verification state, and any uncertainty to the user.

## API reference

The implementation uses the [Jira Cloud REST v3 issue endpoints](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/),
including the project/type-specific create metadata endpoints. Search uses
`POST /rest/api/3/search/jql`; comments use the issue comment endpoint.
