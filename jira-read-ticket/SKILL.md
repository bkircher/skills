---
name: jira-read-ticket
description: Use whenever a user mentions or references a Jira ticket and you want to pull out description, comments, or more.
---

# Instructions for accessing Jira data

Fetch Jira issue data from Atlassian Cloud and receive requested fields in JSON.

## Inputs

- Issue key or a Jira URL
- Environment variables: `ATLASSIAN_URL`, `ATLASSIAN_EMAIL`, `ATLASSIAN_API_TOKEN`

## Workflow

### 1) Identify the issue key
- If the user provides a URL, parse the key (example: `https://.../browse/ABC-123` -> `ABC-123`).
- If the key is missing, ask the user for it.

### 2) Verify environment variables
- Confirm the three environment variables are set; never print the token.
- If missing, ask the user to set them before calling the API.

### 3) Fetch data
You have two options: execute Python scripts or use curl and jq.
- Run scripts/fetch_comments.py which will print all the comments on a ticket
- Run scripts/fetch_assigned_tickets.py which will fetch a list of assigned tickets
- Run scripts/fetch_description.py to fetch a single ticket's description, acceptance criteria, and more details.
- Use REST API v3 with basic auth:
Example: fetch assigned tickets with JQL
<example>
```bash
curl -s \
  -u "$ATLASSIAN_EMAIL:$ATLASSIAN_API_TOKEN" \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  "$ATLASSIAN_URL/rest/api/3/search/jql" \
  --data '{
    "jql": "assignee = currentUser()",
    "fields": ["key", "summary", "status", "issuetype", "project"],
    "maxResults": 100
  }'
```
</example>

Note:
- Use `fields=...` to limit payload when only specific fields are needed.

### 4) Extract results
- The Python scripts return JSON.
- When using `curl`, use `jq` to extract fields of interest.

## Notes

- Jira may return rich text in Atlassian Document Format; use `renderedFields` when a human-readable description is required; otherwise use `fields` as fallback.
- Jira Cloud has removed `/rest/api/3/search`; use `/rest/api/3/search/jql` for JQL search requests. JQL is now POST-only.
- If network access is restricted, rerun API calls with escalated permissions.
- Avoid logging secrets; only reference env var names.
- Only read data from Jira, never alter ticket status or other fields without explicit user approval.
