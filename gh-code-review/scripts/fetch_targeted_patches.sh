#!/usr/bin/env bash
set -euo pipefail
export GH_PAGER=cat GIT_PAGER=cat

usage() {
    printf 'Usage: PR_NUMBER=<number> %s <file> [file ...]\n' "$0" >&2
    printf '   or: %s <number> <file> [file ...]\n' "$0" >&2
}

PR_NUMBER="${PR_NUMBER:-}"
if [ "${1:-}" != "" ] && [[ "${1:-}" =~ ^[0-9]+$ ]]; then
    PR_NUMBER="$1"
    shift
fi

if [ -z "$PR_NUMBER" ] || [ "$#" -lt 1 ]; then
    usage
    exit 2
fi

for cmd in gh jq; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        printf 'Missing required command: %s\n' "$cmd" >&2
        exit 127
    fi
done

gh auth status -h github.com >/dev/null
gh api user --jq .login >/dev/null

files_json=$(gh api "repos/{owner}/{repo}/pulls/$PR_NUMBER/files" --paginate)

printf '### TARGETED_PATCHES\n'
for requested in "$@"; do
    matched=$(printf '%s' "$files_json" | jq -c --arg file "$requested" '
    map(select(.filename == $file)) | .[0] // empty
  ')

    if [ -z "$matched" ]; then
        printf '## %s\n[not found in PR files]\n' "$requested"
        continue
    fi

    printf '%s' "$matched" | jq -r '
    "## " + .filename,
    "status=" + (.status // "unknown") +
      " additions=" + (.additions|tostring) +
      " deletions=" + (.deletions|tostring) +
      " changes=" + (.changes|tostring),
    (.patch // "[no patch available: binary, deleted, or GitHub omitted an oversized patch]"),
    ""
  '
done
