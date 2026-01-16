---
name: jira-write-ticket
description: Use when asked to write a Jira ticket.
---

Generate a Jira ticket description and acceptance criteria using simple Markdown. Strictly follow this order:

- If information is missing or unclear, state this and add numbered, targeted clarification questions.
- Convert any code locations mentioned to GitHub permalinks (e.g., https://github.com/<repo>/blob/<commit>/<file>#L<line>) when possible. If not possible, note this and request more details.
- Find and scan the necessary code to gain more context.
- For referenced Jira tickets, use the jira-read-ticket skill to fetch and summarize details, and include them in a `### Links` section.

Once all question have been clarified follow this structure:

## Description
- Begin with a concise summary based on the provided details.

### Links (if applicable)
- List all referenced Jira tickets with summaries where available.
- Explicitly note missing or unfetched references.

## Acceptance Criteria
- Present concise, bulleted acceptance criteria. Organize as directed by the user or logically.

**Section Order:** Always use this order: Description, Links (if any), Acceptance Criteria.
- Present every section, even if empty; include guidance or clarification questions as needed.
- Number clarification questions.

## Output Format
Use only the following Markdown template, maintaining strict section order:

```markdown
## Description
<Concise ticket summary, or notes/questions if info is missing/unclear>

### Links (if applicable)
- <Linked ticket 1>

## Acceptance Criteria
- <Acceptance criterion 1>
- <Acceptance criterion 2>
- ...
```

- Only use this template. For sections lacking information, call this out and supply numbered clarification questions.
- State and ask if code locations cannot be converted to GitHub permalinks.
