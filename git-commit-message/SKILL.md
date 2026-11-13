---
name: git-commit-message
description: Generate Git commit messages from staged changes.
---

Read the full `git diff --cached`. If empty, report nothing is staged.
Describe only staged changes; use conversation context for why, not extra
changes. Return only the message, without code fences or commentary.

## Checks

Resolve `<script>` to this skill's `scripts/commit_message.py`.
Run it from the target repository.

- Before drafting, run `python3 <script> check_style`. For `"component"`,
  use `<component>: <imperative summary>` for one clear component.
  **Do not use Conventional Commits** (`<type>(<scope>): <description>`,
  scope optional) unless it returns `"conventional"`.
- Before returning, run `python3 <script> validate_format [file]` with the
  draft in a file or on stdin. Fix errors and repeat until success; never
  estimate line lengths.

## Follow Chris Beams' seven rules

1. Separate subject and body with a blank line.
2. Limit the subject to 50 characters.
3. Capitalize unprefixed subjects; preserve exact component names.
4. Do not end the subject with a period.
5. Use the imperative mood: `Fix`, not `Fixed` or `Fixes`.
6. Limit body lines to 72 characters, including indentation.
7. Explain what changed and why, not how.

## Wording and body

Use plain engineering language. Prefer `infra`, `config`, `prod`, and `dev`
when clear. Preserve exact names and repository terminology.

Omit the body only for one small, self-explanatory change. Otherwise, use
`Changes:` with only the necessary `- ` bullets. Do not repeat the subject or
invent details. Omit periods on single-line bullets. Wrap at word boundaries
and indent continuation lines by two spaces.
