# Jira

Skill and command interface for Jira Cloud search, reads, drafting, updates,
creation, and one direct workflow transition per command. Bulk changes,
deletion, comment posting, attachment writes, and issue moves are not
supported.

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
python3 scripts/jira.py transitions ABC-123
python3 scripts/jira.py transition ABC-123 --to-status Done --preview
python3 scripts/jira.py transition ABC-123 --id 31 --input transition.json
python3 scripts/jira.py create --input ticket.json --preview
```

Run these from this skill directory, or use the absolute script path.
See [command and input details](references/commands.md) for snapshots, content
formats, pagination, custom fields, and write result states. Drafting rules are
in [drafting guidance](references/drafting.md).

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
