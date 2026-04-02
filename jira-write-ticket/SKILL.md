---
name: jira-write-ticket
description: "Write a Jira ticket with a structured description, acceptance criteria, GitHub permalinks, and linked ticket summaries. Use when asked to write, draft, or create a Jira ticket, story, bug, task, user story, issue, or backlog item."
---

Generate a Jira ticket in Markdown by following these steps in order:

1. **Gather context** — If information is missing or unclear, state what is missing and ask numbered, targeted clarification questions before drafting.
2. **Resolve code references** — Convert any mentioned code locations to GitHub permalinks (`https://github.com/<repo>/blob/<commit>/<file>#L<line>`). If a permalink cannot be constructed, note this and request the missing details (repo, branch, file, or line).
3. **Scan related code** — Read relevant source files to understand the change area and inform the description.
4. **Fetch linked tickets** — For every referenced Jira ticket, use the `jira-read-ticket` skill to retrieve and summarize it. Include each summary in the Links section.
5. **Draft the ticket** — Once all questions are resolved, produce the ticket using the structure below.

## Ticket structure

Always output these sections in this exact order. Present every section even when empty — add clarification questions as numbered items where information is lacking.

### Description
Write a concise summary of the work to be done based on the provided details. Include GitHub permalinks for any referenced code locations.

### Links (if applicable)
- List each referenced Jira ticket with a one-line summary (fetched via `jira-read-ticket`).
- Explicitly note any references that could not be fetched.

### Acceptance Criteria
- Present concise, bulleted acceptance criteria.
- Organize criteria as directed by the user, or group them logically (e.g., functional, edge cases, non-functional).
