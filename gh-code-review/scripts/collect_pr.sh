#!/usr/bin/env bash
set -euo pipefail
export GH_PAGER=cat GIT_PAGER=cat

usage() {
    printf 'Usage: PR_NUMBER=<number> %s\n' "$0" >&2
    printf '   or: %s <number>\n' "$0" >&2
}

PR_NUMBER="${1:-${PR_NUMBER:-}}"
if [ -z "$PR_NUMBER" ]; then
    usage
    exit 2
fi

MAX_CHANGED_FILES="${MAX_CHANGED_FILES:-20}"
MAX_TOTAL_CHANGES="${MAX_TOTAL_CHANGES:-800}"

for cmd in gh jq; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        printf 'Missing required command: %s\n' "$cmd" >&2
        exit 127
    fi
done

gh auth status -h github.com >/dev/null
gh api user --jq .login >/dev/null

PR_JSON=$(gh pr view "$PR_NUMBER" \
    --json number,title,url,updatedAt,author,baseRefName,headRefName,headRefOid,changedFiles,isDraft,labels,state,reviewDecision,body)

headRefOid=$(printf '%s' "$PR_JSON" | jq -r .headRefOid)
changedFiles=$(printf '%s' "$PR_JSON" | jq -r .changedFiles)

FILES_JSON=$(gh api "repos/{owner}/{repo}/pulls/$PR_NUMBER/files" --paginate)
totalChanges=$(printf '%s' "$FILES_JSON" | jq -s '[.[][].changes] | add // 0')

printf '### PR_JSON\n%s\n' "$PR_JSON"
printf '### HEAD_REF_OID\n%s\n' "$headRefOid"
printf '### FILE_STATS\n'
printf '%s' "$FILES_JSON" |
    jq -r '.[] | [.filename,.status,.additions,.deletions,.changes] | @tsv'

if [ "$changedFiles" -le "$MAX_CHANGED_FILES" ] && [ "$totalChanges" -le "$MAX_TOTAL_CHANGES" ]; then
    printf '### PATCHES\n'
    printf '%s' "$FILES_JSON" |
        jq -r '.[] | "## " + .filename + "\n" + (.patch // "[no patch available]") + "\n"'
else
    printf '### PATCHES_SKIPPED\n'
    printf 'changedFiles=%s totalChanges=%s; inspect targeted patches/files only.\n' "$changedFiles" "$totalChanges"
fi
