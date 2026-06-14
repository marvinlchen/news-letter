#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${PROJECT_ROOT:-}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

PUBLISH_BRANCH="${PUBLISH_BRANCH:-main}"
export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT"

status_file="$PROJECT_ROOT/var/deep-status/latest.json"
if [[ ! -f "$status_file" ]]; then
  echo "publish-deep-report: missing $status_file" >&2
  exit 1
fi

report_date="$(python3 - "$status_file" <<'PY'
import json
import pathlib
import sys
print(json.loads(pathlib.Path(sys.argv[1]).read_text())["date"])
PY
)"
source_report="$PROJECT_ROOT/var/deep-reports/$report_date.md"
if [[ ! -f "$source_report" ]]; then
  echo "publish-deep-report: missing $source_report" >&2
  exit 1
fi

if git remote get-url origin >/dev/null 2>&1; then
  echo "Pulling latest changes..."
  git pull --rebase --autostash origin "$PUBLISH_BRANCH"
fi

mkdir -p published/deep
cp "$source_report" "published/deep/$report_date.md"
cp "$source_report" "published/deep/latest.md"

git add "published/deep/$report_date.md" published/deep/latest.md
if git diff --cached --quiet; then
  echo "publish-deep-report: report is unchanged"
  exit 0
fi

git commit -m "Publish deep reads $report_date"
git push origin "HEAD:$PUBLISH_BRANCH"

echo "Published deep reads for $report_date"
