#!/usr/bin/env bash
set -euo pipefail
export GH_PAGER=cat GIT_PAGER=cat

usage() {
    printf 'Usage: %s <headRefOid> <file[:start[-end]]> [file[:start[-end]] ...]\n' "$0" >&2
}

encode_path() {
    jq -rn --arg path "$1" '$path | split("/") | map(@uri) | join("/")'
}

headRefOid="${1:-}"
if [ -z "$headRefOid" ] || [ "$#" -lt 2 ]; then
    usage
    exit 2
fi
shift

for cmd in gh jq awk; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        printf 'Missing required command: %s\n' "$cmd" >&2
        exit 127
    fi
done

gh auth status -h github.com >/dev/null
gh api user --jq .login >/dev/null

RAW_MAX_LINES="${RAW_MAX_LINES:-400}"

for spec in "$@"; do
    filename="$spec"
    start=""
    end=""

    if [[ "$spec" =~ ^(.+):([0-9]+)(-([0-9]+))?$ ]]; then
        filename="${BASH_REMATCH[1]}"
        start="${BASH_REMATCH[2]}"
        end="${BASH_REMATCH[4]:-${BASH_REMATCH[2]}}"
        if [ "$end" -lt "$start" ]; then
            printf 'Invalid range for %s: end before start\n' "$spec" >&2
            exit 2
        fi
    fi

    if [ -n "$start" ]; then
        printf '\n### FILE %s L%s-L%s\n' "$filename" "$start" "$end"
    else
        printf '\n### FILE %s\n' "$filename"
    fi

    api_path=$(encode_path "$filename")
    if output=$(gh api -H "Accept: application/vnd.github.raw" \
        "repos/{owner}/{repo}/contents/$api_path?ref=$headRefOid" 2>&1); then
        if [ -n "$start" ]; then
            printf '%s\n' "$output" | awk -v s="$start" -v e="$end" \
                'NR >= s && NR <= e { printf "%6d  %s\n", NR, $0 }'
        else
            line_count=$(printf '%s\n' "$output" | awk 'END { print NR }')
            if [ "$line_count" -gt "$RAW_MAX_LINES" ]; then
                printf '[file has %s lines; rerun with %s:start-end for a targeted snippet]\n' \
                    "$line_count" "$filename"
            else
                printf '%s\n' "$output" | awk '{ printf "%6d  %s\n", NR, $0 }'
            fi
        fi
    elif [[ "$output" == *"HTTP 404"* ]]; then
        printf '[not found: %s]\n' "$filename"
    else
        printf '%s\n' "$output" >&2
        exit 1
    fi
done
