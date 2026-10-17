#!/usr/bin/env bash
set -euo pipefail
terms_file=".github/denylist.txt"
if [[ ! -f "$terms_file" ]]; then
  echo "denylist file not present; no terms configured"
  exit 0
fi
mapfile -t terms < <(sed '/^[[:space:]]*$/d' "$terms_file")
files=$(git ls-files | grep -v '^.github/denylist.txt$' || true)
for term in "${terms[@]}"; do
  if [[ -z "$term" ]]; then continue; fi
  if printf '%s\n' "$files" | xargs -r grep -F -i -n -- "$term"; then
    echo "deny-list term found: $term" >&2
    exit 1
  fi
done
