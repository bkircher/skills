# Confluence

Confluence Cloud page search, reads, drafting support, creation, and guarded
updates. This skill is separate from `jira`: pages and issues are different
resources, though both use Atlassian credentials.

Requires Python 3.14 or later and only standard-library modules. Configure:

- `ATLASSIAN_URL`: canonical HTTPS site origin, e.g. `https://example.atlassian.net`.
- `ATLASSIAN_EMAIL`: account email.
- `ATLASSIAN_API_TOKEN`: secret API token.

Do not put credentials in inputs, logs, or version control. Run
`python3 scripts/confluence.py --help` from this skill directory. See
[command and input details](references/commands.md) for examples and limits;
use [drafting guidance](references/drafting.md) for proposed content.

## Transport

Requests use the configured site only. Redirects are refused to avoid
forwarding credentials. Only GET requests can be retried on 429, 502, 503,
or 504. Writes are sent once; a connection or server failure can leave their
result unknown. Error output removes known authentication secrets and query
strings. Search pagination is limited by the requested result count; child-page
pagination follows same-site links only.

Updates use the [Confluence Cloud v2 page API](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/)
and require a matching page version snapshot and the API's next version.
The page is read again after a write. Verification compares the returned title,
body ADF, and relevant ID/version fields. Server-side ADF normalization can
cause a write to be marked unverified; inspect that page manually. Confluence
can reconcile published edits into a draft and may overwrite divergent draft
content. There is no automatic retry for writes.

## Tests

From the repository root:

```sh
python3 -B -W error::ResourceWarning -m unittest discover -s confluence/tests -v
```
