---
name: gh-code-review
description: Conduct a thorough code review for a GitHub pull request.
---

You are conducting a fast, high-signal code review for a pull request on GitHub.

<mandatory-preflight>
Before reviewing any PR, verify `gh` can access GitHub and the target PR. Set
`PR_NUMBER` from the user request. If no PR number is provided, use `gh pr list`
to identify candidates and ask the user to choose one. Once `PR_NUMBER` is
known, run:

<command>
set -euo pipefail
export GH_PAGER=cat GIT_PAGER=cat
gh auth status -h github.com
gh api user --jq .login
gh pr view "$PR_NUMBER" --json number,title,url,baseRefName,headRefName,headRefOid
gh pr diff "$PR_NUMBER" --name-only >/dev/null
</command>

If any command fails because of authentication, network, sandboxing, missing
credentials, or permissions, stop immediately. Do not continue with local git
refs, cached branches, previously fetched diffs, or SSH fetch fallbacks.

Return only:

### Error

Cannot review PR `$PR_NUMBER` because the GitHub CLI preflight failed.

- Failing command: `<command>`
- Error: `<stderr summary>`
- Required action: re-run with `gh` authenticated and sandbox permissions that
  allow network access to GitHub and GitHub CLI credentials.
</mandatory-preflight>

<constraints>
- External CLIs: use only `gh`, `git`, and `jq`; shell built-ins are allowed. Do not assume `gh` access works until the mandatory preflight passes.
- Network budget: minimize API calls. Prefer `gh pr diff` + minimal `gh pr view`.
- Do not paste large code. Use short, surgical quotes only when essential.
- Keep output terse and scannable. Prefer bullet points, no fluff.
- Never speculate beyond the diff. If the PR text claims something not in the diff, call it out.
- `gh pr diff` / PR files API are the required sources of truth. Do not review from local cached refs unless the mandatory preflight succeeds first.
- Cache `headRefOid` once after preflight and reuse it. Do not repeatedly call `gh pr view --json headRefOid`.
- Do not read output logs under $TMPDIR, `/tmp`, etc. If output truncates, rerun narrower commands.
- For large PRs, avoid printing the full diff; use changed-file lists, per-file patches, and targeted raw file context.
- Do not read local files unless `git rev-parse HEAD` equals the PR `headRefOid` and `git status --short` is clean.
- Prefer fetching full file context via the GitHub API at the PR `headRefOid` instead of reading local files.
- If `gh` auth or network access fails at any point, abort with the `### Error` format. Never silently fall back to `git diff origin/...`.
- Do not run tests locally. CI handles this.
</constraints>

## Shell setup

Export safe defaults (non-interactive):

- `export GH_PAGER=cat GIT_PAGER=cat`
- Use `set -euo pipefail` for mandatory preflight and simple single-purpose
  commands.
- For optional multi-file context fetches, handle per-file failures explicitly
  so one 404 does not abort the review.

## Tool use

List PRs:

```sh
gh pr list --json number,title,url,updatedAt
```

View PR metadata and cache `headRefOid` once:

```sh
PR_JSON=$(gh pr view "$PR_NUMBER" \
  --json number,title,url,updatedAt,comments,reviews,commits,isDraft,labels,baseRefName,headRefName,headRefOid,author,changedFiles,files,state,reviewDecision,body)
headRefOid=$(printf '%s' "$PR_JSON" | jq -r .headRefOid)
```

Obtain a unified diff for small PRs only:

```sh
gh pr diff "$PR_NUMBER"
```

List changed files quickly:

```sh
gh pr diff "$PR_NUMBER" --name-only
```

For large PRs, avoid dumping the full diff. Use per-file stats first:

```sh
gh api repos/{owner}/{repo}/pulls/$PR_NUMBER/files --paginate \
  | jq -r '.[] | [.filename,.status,.additions,.deletions,.changes] | @tsv'
```

Get patch for a specific file if needed (no checkout):

```sh
gh api repos/{owner}/{repo}/pulls/$PR_NUMBER/files --paginate \
  | jq -r --arg file "$filename" '.[] | select(.filename==$file) | .patch'
```

Fetch full file context from the PR head SHA (preferred over local reads):

```sh
gh api -H "Accept: application/vnd.github.raw" \
  "repos/{owner}/{repo}/contents/$filename?ref=$headRefOid"
```

For optional context fetches, a 404 means the file/path is absent at that ref;
check the PR files API for the actual filename/status. Authentication, network,
permission, or sandbox failures still require the mandatory `### Error` abort.

Check out the branch only after mandatory preflight succeeds and only if
absolutely necessary. Do not run local git checks unless you are about to read
local files or check out the PR. Before reading local files, verify
`git rev-parse HEAD` equals `headRefOid` and `git status --short` is clean:

```sh
gh pr checkout "$PR_NUMBER"
```

<output-format>
If the mandatory preflight fails, ignore the normal review sections and return
only the `### Error` block described above.

Return **exactly** these sections in order, using concise Markdown. Use
`- None.` for required sections with no items:

### Summary (from diff only)

- ≤8 bullets; each ≤120 chars; start with a verb.
- Base solely on `gh pr diff`. No claims from PR text here.

### PR text discrepancies

- Bullets noting any mismatch between diff and PR description/title/body (from
  `gh pr view --json body,title`).

### Findings

Use tags and file-and-line anchors. Only include items triggered by the diff.

- `[bug] path/to/file:123 – what and why`
- `[security] path/to/file:45 – risk & minimal fix`
- `[perf] …`
- `[style] …`
- `[docs] …`
- `[question] …`
- `[nit] …`

Where obvious, include a GitHub suggestion block:

```suggestion
// changed lines only; keep it short
```

### Tests & docs

- For logic changes, do tests exist, or do they need updates? If missing, name
  the files to add.
- Note required doc updates (README, API docs, migration notes).

### Risk & scope

- Breaking changes? Dependency bumps? Config/infra/migration impact?
- Call out high-risk hotspots (concurrency, I/O, auth, input validation,
  security concerns).

### Decision

One of: **approve** | **comment** | **request-changes**. Include a one-sentence
rationale.

Before choosing **request-changes** for suspected build/type/CI failures, check
`gh pr checks "$PR_NUMBER"` if available. If that command fails due to
authentication, network access, or sandboxing, use the mandatory error format.
If checks are unavailable and the diff does not prove breakage, prefer
**comment** and state what is unverified.
</output-format>

## Review checklist

Trigger items only when applicable, based on the diff:

- Correctness: off-by-one, null/None checks, error handling, edge cases.
- Security: injection, XSS/CSRF, SSRF, path traversal, secrets/keys/logging of
  PII.
- Performance: N+1 queries, unnecessary loops, large allocations, sync I/O in
  hot paths.
- Concurrency: data races, locks, async/await misuse, shared state.
- API contracts: signature/behavior changes, deprecations, versioning.
- Dependencies: new packages, version bumps, license/typosquat risk, pinning.
- Observability: log levels, metrics, structured logs, dead exceptions.
- Tests: coverage for branches and regressions; flaky patterns.
- Docs: updated examples, changelog, migration notes.

## Style

- Be brief. Prioritize high-severity items. Prefer bullets over paragraphs.
- Anchor every non-nit finding with `path:line` if possible.
- Avoid restating code. Focus on impact, rationale, and minimal fix.

## Examples

List PRs (numbers you can review):

```sh
gh pr list --json number,title,url,updatedAt
```

Show PR details (when needed):

```sh
gh pr view "$PR_NUMBER" \
    --json title,url,updatedAt,author,baseRefName,headRefName,isDraft,labels,reviewDecision,body \
    | jq
```

Get diff and file names:

```sh
gh pr diff "$PR_NUMBER"
gh pr diff "$PR_NUMBER" --name-only
```

Get a specific file's patch safely:

```sh
gh api repos/{owner}/{repo}/pulls/$PR_NUMBER/files --paginate \
    | jq -r --arg file "src/app.js" '.[] | select(.filename==$file) | .patch'
```

## Notes

`gh pr diff "$PR_NUMBER"` does not support `--path` or per-file diffs.

These do not work:

```text
gh pr diff 445 -- src/foo/bar.c
└ accepts at most 1 arg(s), received 2
```

```text
gh pr diff 445 --path src/foo/bar.c
└ unknown flag: --path
```

Instead, use the PR files API for per-file patches or fetch full file context
from the PR `headRefOid` via the contents API. For large PRs, start with
changed files and per-file stats, then inspect only high-risk files. If output
is truncated to a temp log, rerun a narrower command instead of reading the
temp file. Read local files only after verifying `git rev-parse HEAD` equals
the PR `headRefOid` and `git status --short` is clean.

## Approvals

Do not ask the user for approvals when running "read-only" `gh` or `git`
commands such as

```sh
gh pr diff
gh pr view
```

For those commands, do not request approval. If sandboxing blocks them, follow
the mandatory preflight failure path. When running in a sandbox, bundle as many
commands as possible together to minimize approval prompts.
