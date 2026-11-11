#!/usr/bin/env bash
# Fire the scheduled task with a brief, then wait for the branch it pushes.
# Usage: fire.sh BRIEF_FILE BRANCH REMOTE
# Needs ROUTINE_FIRE_URL and ROUTINE_FIRE_TOKEN in the environment.
set -euo pipefail
brief_file=$1; branch=$2; remote=$3
: "${ROUTINE_FIRE_URL:?}" "${ROUTINE_FIRE_TOKEN:?}"
body=$(jq -Rs '{text: .}' < "$brief_file")
started=$(date +%s)
curl -sSf -X POST "$ROUTINE_FIRE_URL" \
  -H "Authorization: Bearer $ROUTINE_FIRE_TOKEN" \
  -H "anthropic-version: 2026-10-21" \
  -H "Content-Type: application/json" \
  -d "$body" | jq .
for _ in $(seq 1 120); do
  if git ls-remote --exit-code --heads "$remote" "$branch" >/dev/null 2>&1; then
    echo "branch $branch appeared after $(( $(date +%s) - started )) s"
    exit 0
  fi
  sleep 30
done
echo "no branch $branch after 60 minutes" >&2
exit 1
