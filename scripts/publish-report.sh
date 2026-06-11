#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/finance-news-digest}"
PUBLISH_BRANCH="${PUBLISH_BRANCH:-main}"
export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT"

status_file="$PROJECT_ROOT/var/status/latest.json"
if [[ ! -f "$status_file" ]]; then
  echo "publish-report: missing $status_file" >&2
  exit 1
fi

report_date="$(
  python3 - "$status_file" <<'PY'
import json
import pathlib
import sys

print(json.loads(pathlib.Path(sys.argv[1]).read_text())["date"])
PY
)"
source_report="$PROJECT_ROOT/var/digests/$report_date.md"
if [[ ! -f "$source_report" ]]; then
  echo "publish-report: missing $source_report" >&2
  exit 1
fi

if git remote get-url origin >/dev/null 2>&1; then
  git pull --rebase --autostash origin "$PUBLISH_BRANCH"
fi

mkdir -p reports
cp "$source_report" "reports/$report_date.md"
cp "$source_report" "reports/latest.md"

git add "reports/$report_date.md" reports/latest.md
if git diff --cached --quiet; then
  echo "publish-report: report is unchanged"
  exit 0
fi

git commit -m "Publish finance digest $report_date"
git push origin "HEAD:$PUBLISH_BRANCH"
