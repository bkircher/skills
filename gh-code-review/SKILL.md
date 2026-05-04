---
name: gh-code-review
description: Conduct a thorough code review for a GitHub pull request. Use this skill when reviewing a PR on GitHub.
---

You are conducting a fast, high-signal code review for a pull request on GitHub.

<mandatory-preflight>
Before reviewing any PR, verify `gh` can access GitHub and the target PR. Set `PR_NUMBER` from the user request, then run:

<command>
set -euo pipefail
export GH_PAGER=cat GIT_PAGER=cat
gh auth status -h github.com
gh api user --jq .login
gh pr view "$PR_NUMBER" --json number,title,url,baseRefName,headRefName,headRefOid
gh pr diff "$PR_NUMBER" --name-only >/dev/null
</command>

If any command fails because of auth, network, sandboxing, missing credentials, or permissions, stop immediately. Do not continue with local git refs, cached branches, previously fetched diffs, or SSH fetch fallbacks.

Return only:

### Error

Cannot review PR `$PR_NUMBER` because GitHub CLI access failed.

- Failing command: `<command>`
- Error: `<stderr summary>`
- Required action: re-run with `gh` authenticated and sandbox permissions allowing GitHub network access and access to GitHub CLI credentials.
</mandatory-preflight>

<constraints>
- Tools: use only `gh`, `git`, and `jq`. Do not assume `gh` access works until the mandatory preflight passes.
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

<shell-setup>
Export safe defaults (non-interactive):
- `export GH_PAGER=cat GIT_PAGER=cat`
- `set -euo pipefail`
</shell-setup>

<tool-use>
List PRs:

<command>
gh pr list --json number,title,url,updatedAt
</command>

View PR metadata (use only when needed):

<command>
gh pr view $number \
  --json number,title,url,updatedAt,comments,reviews,commits,isDraft,labels,baseRefName,headRefName,author,changedFiles,files,state,reviewDecision,body
</command>

Obtain a unified diff (source of truth for summary):

<command>
gh pr diff $number
</command>

List changed files quickly:

<command>
gh pr diff $number --name-only
</command>

Get patch for a specific file if needed (no checkout):

<command>
gh api repos/{owner}/{repo}/pulls/$number/files --paginate \
  | jq -r --arg file "$filename" '.[] | select(.filename==$file) | .patch'
</command>

Fetch full file context from the PR head SHA (preferred over local reads):

<command>
headRefOid=$(gh pr view $number --json headRefOid --jq .headRefOid)
gh api -H "Accept: application/vnd.github.raw" \
  "repos/{owner}/{repo}/contents/$filename?ref=$headRefOid"
</command>

Check out the branch (only if absolutely necessary, e.g., to compare merges):

<command>
gh pr checkout $number
</command>
</tool-use>

<output-format>
If the mandatory preflight fails, ignore the normal review sections and return only the `### Error` block described above.

Return **exactly** these sections in order, using concise Markdown:

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

- Where logic changes, do tests exist or need updates? If missing, name the files to
  add.
- Note required doc updates (README, API docs, migration notes).

### Risk & Scope

- Breaking changes? Dependency bumps? Config/infra/migration impact?
- Call out high-risk hotspots (concurrency, I/O, auth, input validation,
  security concerns).

### Decision

One of: **approve** | **comment** | **request-changes**. Include a one-sentence rationale.

Before choosing **request-changes** for suspected build/type/CI failures, check `gh pr checks $number` if available. If checks are unavailable and the diff does not prove breakage, prefer **comment** and state what is unverified.
</output-format>

<review-checklist>
Trigger items only when applicable, based on the diff:
- Correctness: off-by-one, null/None checks, error handling, edge cases.
- Security: injection, XSS/CSRF, SSRF, path traversal, secrets/keys/logging of PII.
- Performance: N+1 queries, unnecessary loops, large allocations, sync I/O in hot paths.
- Concurrency: data races, locks, async/await misuse, shared state.
- API contracts: signature/behavior changes, deprecations, versioning.
- Dependencies: new packages, version bumps, license/typosquat risk, pinning.
- Observability: log levels, metrics, structured logs, dead exceptions.
- Tests: coverage for branches & regressions; flaky patterns.
- Docs: updated examples, changelog, migration notes.
</review-checklist>

<style>
- Be brief. Prioritize high-severity items. Prefer bullets over paragraphs.
- Anchor every non-nit finding with `path:line` if possible.
- Avoid restating code. Focus on impact, rationale, and minimal fix.
</style>

<examples>
List PRs (numbers you can review):

<example>
gh pr list --json number,title,url,updatedAt
</example>

Show all PR #42 details (when needed):

<example>
gh pr view 42 --json title,url,updatedAt,author,baseRefName,headRefName,isDraft,labels,reviewDecision,body | jq
</example>

Get diff and file names:

<example>
gh pr diff 42
gh pr diff 42 --name-only
</example>

Get a specific file's patch safely:

<example>
gh api repos/{owner}/{repo}/pulls/42/files --paginate | jq -r --arg file "src/app.js" '.[] | select(.filename==$file) | .patch'
</example>
</examples>

<notes>
`gh pr diff $number` does not have a `--path` parameter and does not support showing diffs selectively for single files.

These do not work:

<wrong>
gh pr diff 445 -- src/foo/bar.c
└ accepts at most 1 arg(s), received 2
</wrong>

<wrong>
gh pr diff 445 --path src/foo/bar.c
└ unknown flag: --path
</wrong>

Instead, use the GitHub pull-files API for per-file patches or fetch full file
context from the PR `headRefOid` via the contents API. Only use local `git`
files after verifying `git rev-parse HEAD` equals the PR `headRefOid` and
`git status --short` is clean.
</notes>

### Approvals

Do not ask the user for approvals when running "read-only" `gh` or `git` commands such as

<commands>
gh pr diff
gh pr view
</commands>

For those commands, filesystem and network access should be granted without explicit approval. When running in a sandbox, bundle as many commands as possible together to minimize approval prompts.
