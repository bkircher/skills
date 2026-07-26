---
name: git-commit-message
description: Generate Git commit messages from staged changes when requested.
---

Create a commit message for the staged changes. If changes are staged, return
only the commit message, with no code fence or commentary. Otherwise, report
that nothing is staged.

## Inspect the staged changes

List the staged files:

<command>
git diff --cached --name-only
</command>

If this produces no output, report that nothing is staged and do not invent a
message. Otherwise, read the complete staged diff:

<command>
git diff --cached
</command>

Use the conversation context to understand the rationale, but describe only the
staged diff. Ignore unstaged and untracked changes.

## Inspect the repository style

Read recent non-merge commit subjects before drafting the message:

<command>
git log -30 --no-merges --format=%s
</command>

Match the established style. Use Conventional Commit syntax such as
`feat(scope): ...` or `fix(scope): ...` only when it clearly dominates recent
history. Isolated examples and component prefixes such as `subdir: ...` do not
establish that convention.

## Use concise, natural language

- Prefer plain, slightly informal engineering language over formal wording.
- When unambiguous, prefer `infra`, `config`, `prod`, and `dev` over
  `infrastructure`, `configuration`, `production`, and `development`.
- Preserve exact names from the staged diff and follow established repository
  terminology when it differs.

## Write the subject

- Limit the subject to 50 characters.
- Use the imperative mood: `fix`, not `fixed` or `fixes`.
- Do not end the subject with a period.
- When changes affect one clear component and history uses component prefixes,
  use `<component>: <imperative summary>` and match the casing used in recent
  history. Otherwise, capitalize the first word of an unprefixed subject.

## Write the body

Use this format unless the subject fully describes one small,
self-explanatory change:

```text
<subject>

Changes:
- <change or rationale>
- <change or rationale>
```

- Separate the body from the subject with a blank line.
- Keep every body line within 72 characters, including indentation.
- Explain what changed and why without repeating the subject or including
  unnecessary implementation details.
- Use only as many bullets as needed; do not invent items to reach a fixed
  count.
- Do not end a one-line bullet with a period.
- Wrap bullets at word boundaries and indent continuation lines by two spaces.

## Validate the message

Before returning the message, run `scripts/validate_commit_message.py`. Resolve
its path relative to this `SKILL.md` directory and provide the draft through
standard input or in a file:

```sh
python3 /path/to/git-commit-message/scripts/validate_commit_message.py \
  /path/to/draft-message
```

Revise and rerun the validator until it exits successfully. Never estimate line
lengths manually.

## Example

```text
git-commit-message: improve guidance

Changes:
- Match subject formatting to established repository history
- Validate commit message formatting before returning the result
- Avoid Conventional Commit syntax unless the project clearly uses it
```
