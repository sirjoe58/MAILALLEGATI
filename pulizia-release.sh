#!/usr/bin/env bash
# Tiene solo le ultime 2 versioni pubblicate di ogni app del repository.
# Le app si riconoscono dal prefisso del tag: v1.2.3, planner-v1.2.3, training-v1.2.3, tutorial-v1.0.0 ...
# Uso: GH_TOKEN=... bash tools/pulizia-release.sh owner/repo
set -euo pipefail
REPO="$1"
gh release list --repo "$REPO" --limit 200 --json tagName,createdAt \
  --jq 'sort_by(.createdAt) | reverse | .[].tagName' > /tmp/tags.txt
declare -A COUNT
while read -r tag; do
  [ -z "$tag" ] && continue
  prefix="${tag%%v[0-9]*}"          # "" per v1.2.3, "planner-" per planner-v1.2.3
  COUNT[$prefix]=$(( ${COUNT[$prefix]:-0} + 1 ))
  if [ "${COUNT[$prefix]}" -gt 2 ]; then
    echo "Elimino la vecchia versione $tag"
    gh release delete "$tag" --repo "$REPO" --yes --cleanup-tag || true
  fi
done < /tmp/tags.txt
