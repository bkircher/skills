# Jira

One skill and command interface for Jira Cloud search, reads, drafting, updates,
and creation. Bulk changes, deletion, comment posting, status transitions,
attachment writes, and issue moves are not supported.

## Requirements

Use Python 3.14 or later. Only standard-library modules are required.

Set these environment variables:

- `ATLASSIAN_URL`: the canonical HTTPS Jira site, such as `https://example.atlassian.net`.
  Do not include a path, query, fragment, or credentials.
- `ATLASSIAN_EMAIL`: the account email.
- `ATLASSIAN_API_TOKEN`: the secret API token.

The client checks these variables together, without a separate API request.
Never print or store credentials in inputs, logs, or version control.

## Commands

```sh
python3 scripts/jira.py --help
python3 scripts/jira.py search --assignee me --open
python3 scripts/jira.py get ABC-123 --comments
python3 scripts/jira.py metadata --project ABC --issue-type Task
python3 scripts/jira.py update ABC-123 --input changes.json --preview
python3 scripts/jira.py create --input ticket.json --preview
```

Run these from this skill directory, or use the absolute script path.
See [command and input details](references/commands.md) for snapshots, content
formats, pagination, custom fields, and write result states. Drafting rules are
in [drafting guidance](references/drafting.md).

Applied updates require a source snapshot from `get --for-update` or a preview.
They validate edit metadata, skip unchanged values, write once, and verify the
saved fields. Creation validates project/type metadata and verifies the new issue.
Neither operation retries an uncertain write.

## Modules

- `scripts/jira.py`: argument handling, JSON input, results, and exit codes.
- `scripts/client.py`: the single authenticated REST v3 HTTP client.
- `scripts/issues.py`: search, read, comments, snapshots, and write verification.
- `scripts/metadata.py`: field and issue-type discovery with per-invocation caching.
- `scripts/changes.py`: input validation and write payload construction.
- `scripts/rich_text.py`: a limited Markdown writer and section-preserving ADF edits.
- `scripts/adf.py`: readable Markdown output. This is not a lossless editing format.

No command accepts arbitrary endpoints. Write payloads cannot contain transitions,
comments, worklogs, bulk issue lists, or unrelated API actions.

## Client behavior

- The client normalizes surrounding whitespace and trailing site slashes. It does
  not guess aliases. All requests must use HTTPS on the configured site.
- Automatic redirects are disabled for every method. A redirect error identifies
  the proposed HTTPS site when possible. Verify it before changing `ATLASSIAN_URL`.
  Credentials are not forwarded to a redirect target.
- The default socket timeout is 30 seconds, not a total operation deadline.
- Only HTTP `429`, `502`, `503`, and `504` can be retried, and only for `GET`,
  `HEAD`, or `POST /rest/api/3/search/jql`. The default maximum is two retries.
- Retry delays start at one second and double. A valid `Retry-After` takes
  precedence. A requested delay above 30 seconds stops automatic retries rather
  than causing an early retry.
- Authentication failures, permission failures, transport errors, and writes are
  not retried. An uncertain result requires review before another write.
- Error diagnostics remove known authentication secrets and omit request query
  strings. Invalid JSON errors do not include the response body.
- `request_json()` returns `None` for an empty success, including HTTP `204`.
  `request_object()` and `request_array()` still require their respective types.

Library callers can configure `timeout` and `max_retries` as client keyword
arguments. Metadata caches belong to one authenticated client and invocation;
there is no disk cache or cached permission state between commands.

## Tests

From the repository root:

```sh
python3 -B -W error::ResourceWarning -m unittest discover -s jira/tests -v
```

Tests simulate HTTP responses, clocks, retry delays, environment variables, and
input files. They do not contact Jira or require real credentials. CI runs the
suite on Python 3.14. No live write test is performed by default.

## Migration

This skill replaces `jira-read-ticket` and `jira-write-ticket`. Their instructions
are now in this skill and its references. The old fetch scripts are replaced by
`get` and `search`; their old command names and JSON shapes are not retained.
The previous HTTP client implementation is now `scripts/client.py`.

If an installation links individual skill directories, change its old link to
this `jira` directory and reload the installed skills. Repository-wide skill
links need no directory change. External installation links are not modified by
this repository change.
