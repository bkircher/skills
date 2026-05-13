---
name: gh-code-review
description: Review GitHub pull requests using gh CLI and the GitHub API. Use when asked to review a PR, inspect PR changes, or choose approve/comment/request-changes.
---

You are conducting a fast, high-signal code review for a GitHub pull request.

## Hard rules

- Use the scripts in this skill for deterministic GitHub data collection:
  - `scripts/collect_pr.sh` for mandatory preflight and first-pass PR data.
  - `scripts/fetch_targeted_patches.sh` for large-PR targeted patch context.
  - `scripts/fetch_raw_files.sh` for optional targeted raw-file snippets.
- Resolve script paths relative to this `SKILL.md` directory.
- Standard reviews are API-only: use PR Files API patches and GitHub Contents
  API at the PR `headRefOid` as sources of truth, but access them through the
  scripts above rather than ad hoc `gh api` commands.
- Do not run `gh pr checkout`, `git fetch`, `git checkout`, tests, or read local
  repository source files during a standard review.
- Do not review from local cached refs, cached branches, or `git diff` output.
- Do not run recursive repository tree/content scans or broad search pipelines
  over GitHub Contents API output.
- Do not manually call the PR Files API, `gh pr diff`, or GitHub Contents API.
  If script output is incomplete, use the sanctioned targeted script below.
- Do not paste large code. Use short, surgical quotes.
- Never speculate beyond collected patches/file stats. If PR text claims
  something not shown by patches, call it out.
- If any GitHub command fails because of authentication, network, sandboxing,
  missing credentials, or permissions, stop immediately and return only the
  error block below.

```markdown
### Error

Cannot review PR `$PR_NUMBER` because the GitHub/script preflight failed.

- Failing command: `<command>`
- Error: `<stderr summary>`
- Required action: rerun with required commands available, `gh` authenticated,
  and sandbox permissions that allow network access to GitHub and GitHub CLI
  credentials.
```

## Workflow

### 1. Identify the PR

Set `PR_NUMBER` from the user request. If no PR number is provided, run only:

```sh
gh pr list --json number,title,url,updatedAt
```

Then ask the user to choose a PR.

### 2. Run mandatory preflight and data collection

After `PR_NUMBER` is known, run `scripts/collect_pr.sh`. This script verifies
GitHub CLI access, retrieves PR metadata, file stats, and patches when the PR is
reasonably sized. It replaces ad hoc `gh pr view`, `gh pr diff`, and repeated PR
Files API calls.

Use either form:

```sh
PR_NUMBER=123 /path/to/gh-code-review/scripts/collect_pr.sh
# or
/path/to/gh-code-review/scripts/collect_pr.sh 123
```

Use the script output as the normal review input:

- `PR_JSON`: metadata, title/body, cached `headRefOid`.
- `HEAD_REF_OID`: pass this to `scripts/fetch_raw_files.sh` if needed.
- `FILE_STATS`: changed files and additions/deletions.
- `PATCHES`: per-file patches for review.
- `PATCHES_SKIPPED`: large PR; choose a small target set from `FILE_STATS` and
  fetch only those patches with `scripts/fetch_targeted_patches.sh`.

If output is truncated, do not read temp logs and do not compensate with broad
API calls. Use the targeted scripts below. If no concrete issue is visible from
collected patches, stop and write the review.

### 3. For `PATCHES_SKIPPED`, fetch targeted patches only

When `collect_pr.sh` skips patches, do not manually call the PR Files API and do
not refetch/output every changed file's patch. Pick a small set of paths
justified by `FILE_STATS` and PR metadata, then batch them in one sanctioned
call:

```sh
PR_NUMBER=123 /path/to/gh-code-review/scripts/fetch_targeted_patches.sh \
  "path/to/file1" \
  "path/to/file2"
```

Use the returned `TARGETED_PATCHES` as patch context. If a targeted file reports
`[no patch available]`, treat it as unreviewable from patches unless raw context
is needed for a specific nearby issue. Deleted files cannot be fetched from the
head ref; review their removal from the targeted patch if available.

### 4. Fetch targeted raw-file snippets only when needed

Fetch raw context only for files where a collected patch suggests a specific
possible issue. Prefer `file:start-end` snippets around the relevant lines; full
files are line-capped to avoid tool-output truncation. Batch all needed snippets
in one invocation. Do not fetch files merely to be more thorough.

```sh
/path/to/gh-code-review/scripts/fetch_raw_files.sh "$HEAD_REF_OID" \
  "path/to/file1:40-90" \
  "path/to/file2:120-160"
```

A 404 means the file path is absent at that ref; check collected PR file stats
for the actual filename or status. Authentication, network, permission, or
sandbox failures still require the mandatory `### Error` response.

### 5. Optional checks

Only call `gh pr checks "$PR_NUMBER"` before choosing **request-changes** for
suspected build, type, or CI failures. Do not call it routinely. If checks are
unavailable and collected patches do not prove breakage, prefer **comment** and
state what is unverified.

## Call budget

Target for a normal review after `PR_NUMBER` is known:

- One mandatory `scripts/collect_pr.sh` invocation.
- One optional `scripts/fetch_targeted_patches.sh` invocation when
  `PATCHES_SKIPPED` is present.
- One optional `scripts/fetch_raw_files.sh` invocation for targeted snippets.
- One optional `gh pr checks "$PR_NUMBER"` call only as described above.

Do not repeat `gh pr view`, manually call the PR Files API or Contents API, run
`gh pr diff`, or perform repo-wide tree/content scans.

## Review focus

Trigger items only when applicable, based on collected patches:

- Correctness: edge cases, null/None checks, error handling, off-by-one issues.
- Security: injection, XSS/CSRF, SSRF, path traversal, secrets, PII logging.
- Performance: N+1 queries, needless loops, large allocations, hot-path sync
  I/O.
- Concurrency: races, locks, async/await misuse, shared state.
- API contracts: signature/behavior changes, deprecations, versioning.
- Dependencies: new packages, version bumps, licensing or typosquatting risk,
  pinning.
- Observability: log levels, metrics, structured logs, swallowed exceptions.
- Tests and docs: missing regression coverage, examples, changelog, migration
  notes.

## Output format

Return exactly these sections in order, using concise Markdown. Use `- None.`
for required sections with no items.

### Summary (from patches only)

- ≤8 bullets; each ≤120 chars; start with a verb.
- Base solely on collected patches/file stats. No claims from PR text here.

### PR text discrepancies

- List mismatches between collected patches and PR title/body from `PR_JSON`.

### Findings

Use tags and file-and-line anchors. Only include items triggered by collected
patches.

- `[bug] path/to/file:123 – what and why`
- `[security] path/to/file:45 – risk & minimal fix`
- `[perf] …`
- `[style] …`
- `[docs] …`
- `[question] …`
- `[nit] …`

Where obvious, include a short GitHub suggestion block with changed lines only.

### Tests & docs

- For logic changes, state whether tests exist or need updates. If missing, name
  the files to add.
- Note required doc updates such as README, API docs, or migration notes.

### Risk & scope

- Call out breaking changes, dependency bumps, configuration, infrastructure, or
  migration impact.
- Note high-risk hotspots: concurrency, I/O, auth, input validation, security.

### Decision

Use one of: **approve** | **comment** | **request-changes**. Include a
one-sentence rationale.

## Style

- Be brief. Prioritize high-severity items. Prefer bullets over paragraphs.
- Anchor every non-nit finding with `path:line` if possible.
- Avoid restating code. Focus on impact, rationale, and minimal fix.
- Do not ask for approval before running the read-only `gh` commands/scripts; if
  sandboxing blocks them, use the mandatory error format.
