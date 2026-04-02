---
name: gh-address-comments
description: "Address review and issue comments on the open GitHub PR for the current branch using gh CLI. Reply to reviewer feedback, push code fixes, and resolve review conversations. Verify gh auth first and prompt the user to authenticate if not logged in. Use when the user asks to respond to PR feedback, address reviewer comments, fix issues raised in a review, or resolve review conversations."
metadata:
  short-description: Address comments in a GitHub PR review
---

# PR Comment Handler

Guide to find the open PR for the current branch and address its comments with gh CLI. Run all `gh` commands with elevated network access.

## Prerequisites

Ensure `gh` is authenticated (run `gh auth login` once if needed), then verify access:

```bash
gh auth status
```

Confirm workflow/repo scopes are included so `gh` commands succeed. If sandboxing blocks `gh auth status`, rerun it with `sandbox_permissions=require_escalated`.

Identify the current PR:

```bash
gh pr view --json number,url,title,state
```

## 1) Inspect comments needing attention

Run the bundled script to fetch all conversation comments, reviews, and inline review threads:

```bash
python scripts/fetch_comments.py
```

The script uses `gh api graphql` to retrieve top-level conversation comments, review submissions (approve/request changes/comment), and inline review threads with resolved status, file path, and line numbers.

**Fallback** — if the script is unavailable, fetch comments directly:

```bash
# Top-level PR comments
gh api repos/{owner}/{repo}/pulls/{number}/comments

# Review comments (inline)
gh api repos/{owner}/{repo}/pulls/{number}/reviews

# Issue-style comments on the PR
gh api repos/{owner}/{repo}/issues/{number}/comments
```

Replace `{owner}`, `{repo}`, and `{number}` with values from `gh pr view --json headRepositoryOwner,headRepository,number`.

## 2) Ask the user for clarification

- Number all review threads and comments sequentially.
- For each item, provide:
  - The file and line reference (for inline comments).
  - The reviewer's username and comment summary.
  - A short description of what fix or response would be needed.
- Ask the user which numbered comments should be addressed.

## 3) Apply fixes for selected comments

For each selected comment:

1. **Make the code change** — edit the relevant file(s) to address the reviewer's feedback.
2. **Reply to the review thread** to explain what was changed:

   ```bash
   gh api repos/{owner}/{repo}/pulls/{number}/comments/{comment_id}/replies \
     -f body="Fixed — <brief explanation of the change>"
   ```

3. **Resolve the review thread** if the fix fully addresses the feedback:

   ```bash
   gh api graphql -f query='mutation { resolveReviewThread(input: {threadId: "<thread_node_id>"}) { thread { isResolved } } }'
   ```

4. **Commit and push** the changes:

   ```bash
   git add <changed-files>
   git commit -m "address review: <short summary>"
   git push
   ```

## 4) Validate fixes

After applying all fixes, verify the PR is in good shape:

1. **Run tests** locally to confirm nothing is broken:

   ```bash
   # Use the project's test command (e.g., npm test, pytest, make test)
   ```

2. **Check CI status** on the PR:

   ```bash
   gh pr checks
   ```

3. **Review the updated diff** to confirm changes look correct:

   ```bash
   gh pr diff
   ```

4. If any checks fail, investigate and fix before notifying the user.

## Notes

- If `gh` hits auth or rate-limit issues mid-run, prompt the user to re-authenticate with `gh auth login`, then retry.
- Only resolve threads when the fix fully addresses the feedback. If partial, reply explaining what was done and what remains.
- When multiple comments relate to the same issue, group them into a single fix and reference all related threads in the reply.
