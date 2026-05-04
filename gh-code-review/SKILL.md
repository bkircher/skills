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
  allow GitHub network access and access to GitHub CLI credentials.
</mandatory-preflight>

<constraints>
- External CLIs: use only `gh`, `git`, and `jq`; shell built-ins are allowed. Do not assume `gh` access works until the mandatory preflight passes.
- Network budget: minimize API calls. Prefer `gh pr diff` + minimal `gh pr view`.
- Do not paste large code. Use short, surgical quotes only when essential.
- Keep output terse and scannable. Prefer bullet points, no fluff.
- Never speculate beyond the diff. If the PR text claims something not in the diff, call it out.
- `gh pr diff` is the required source of truth. Do not review from local cached refs unless the mandatory preflight succeeds first.
- Do not read local files unless `git rev-parse HEAD` equals the PR `headRefOid` and `git status --short` is clean.
- Prefer fetching full file context via the GitHub API at the PR `headRefOid` instead of reading local files.
- If `gh` auth or network access fails at any point, abort with the `### Error` format. Never silently fall back to `git diff origin/...`.
- Do not run tests locally. The CI pipeline takes care of this.
</constraints>

## Shell Setup

Export safe defaults (non-interactive):

- `export GH_PAGER=cat GIT_PAGER=cat`
- `set -euo pipefail`

## Tool Use

List PRs:

```sh
gh pr list --json number,title,url,updatedAt
```

View PR metadata (use only when needed):

```sh
gh pr view "$PR_NUMBER" \
  --json number,title,url,updatedAt,comments,reviews,commits,isDraft,labels,baseRefName,headRefName,author,changedFiles,files,state,reviewDecision,body
```

Obtain a unified diff (source of truth for summary):

```sh
gh pr diff "$PR_NUMBER"
```

List changed files quickly:

```sh
gh pr diff "$PR_NUMBER" --name-only
```

Get patch for a specific file if needed (no checkout):

```sh
gh api repos/{owner}/{repo}/pulls/$PR_NUMBER/files --paginate \
  | jq -r --arg file "$filename" '.[] | select(.filename==$file) | .patch'
```

Fetch full file context from the PR head SHA (preferred over local reads):

```sh
headRefOid=$(gh pr view "$PR_NUMBER" --json headRefOid --jq .headRefOid)
gh api -H "Accept: application/vnd.github.raw" \
  "repos/{owner}/{repo}/contents/$filename?ref=$headRefOid"
```

Check out the branch only after mandatory preflight succeeds and only if
absolutely necessary. Before reading local files, verify `git rev-parse HEAD`
equals `headRefOid` and `git status --short` is clean:

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

### PR Text Discrepancies

- Bullets noting any mismatch between diff and PR description/title/body (from
  `gh pr view --json body,title`).

### Findings

Use tags and file/line anchors. Only include items triggered by the diff.

- `[bug] path/to/file:123 – what & why`
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

### Tests & Docs

- For logic changes, do tests exist or need updates? If missing, name the files
  to add.
- Note required doc updates (README, API docs, migration notes).

### Risk & Scope

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

## Review Checklist

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
- Tests: coverage for branches & regressions; flaky patterns.
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

`gh pr diff "$PR_NUMBER"` does not have a `--path` parameter and does not
support showing diffs selectively for single files.

These do not work:

```text
gh pr diff 445 -- src/foo/bar.c
└ accepts at most 1 arg(s), received 2
```

```text
gh pr diff 445 --path src/foo/bar.c
└ unknown flag: --path
```

Instead, use the GitHub pull-files API for per-file patches or fetch full file
context from the PR `headRefOid` via the contents API. Only use local `git`
files after verifying `git rev-parse HEAD` equals the PR `headRefOid` and
`git status --short` is clean.

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
