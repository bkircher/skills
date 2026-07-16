---
name: snyk-cli

description: Scan and triage Snyk security findings in local repositories and container images. Use for Snyk vulnerability reviews, scan summaries, severity filtering, and remediation planning.
---

Use Snyk to scan the current repository. Default to read-only operations; do not ignore, delete, import, monitor, or modify Snyk data unless the user explicitly requests it.

## Authentication

Snyk CLI uses OAuth and authenticates through the browser.

```sh
snyk auth
```

## Local repository scans

First, check whether the CLI is installed:

```bash
command -v snyk >/dev/null 2>&1
```

Do not install or upgrade the CLI unless the user asks.

Select only commands relevant to the repository:

```bash
# Open-source dependencies
snyk test --json

# Static application security testing
snyk code test --json

# Infrastructure as code
snyk iac test --json

# Container image; replace IMAGE with the requested image
snyk container test IMAGE --json
```

Do not run `monitor`, `--report`, imports, ignores, or other persistent operations unless explicitly requested.

Treat exit code `1` from Snyk test commands as a completed scan with findings, not as an execution failure. Treat other non-zero codes as command failures unless the command documentation states otherwise.

For large JSON output, save it to a temporary file outside the repository and summarize it with `jq`. Delete temporary files after use.

## Workflow

1. Identify the scan types relevant to the current repository or requested container image.
2. Validate authentication without exposing credentials.
3. Run the smallest read-only scan that answers the request.
4. Normalize findings by product, project, severity, issue type, exploit maturity, fix availability, package or file, and identifier when those fields are present.
5. Deduplicate repeated findings while preserving affected projects and paths.
6. Prioritize results in this order:
   - Critical with a fix available
   - High with a fix available
   - Critical or high without a fix
   - Medium
   - Low
7. Distinguish direct evidence returned by Snyk from remediation suggestions inferred from repository context.
8. Report incomplete access, unsupported project types, and failed scans explicitly.

## Output format

For a scan or issue review, return:

- Scope: project, path, image, or repository scanned
- Result: passed, findings present, or scan failed
- Counts by severity
- Highest-priority findings with location and fix guidance
- Fix availability and upgrade target when supplied by Snyk
- Commands run, with secrets removed

Keep the default output concise. Do not paste full raw JSON unless requested.

## Safety rules

- Default to read-only behavior.
- Require explicit user intent before any operation that changes Snyk state or uploads repository metadata.
- Never weaken a security policy, ignore a finding, or suppress a scan result without explicit instruction.
- Do not treat an ignored or accepted issue as fixed.
- Do not expose repository source, dependency manifests, or findings beyond what is necessary for the task.
