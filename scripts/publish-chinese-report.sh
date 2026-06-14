#!/usr/bin/env bash
set -euo pipefail

# 动态检测项目根目录
if [[ -z "${PROJECT_ROOT:-}" ]]; then
  # 从脚本位置推断项目根目录
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

PUBLISH_BRANCH="${PUBLISH_BRANCH:-main}"
export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT"

echo "Publish Chinese report from: $PROJECT_ROOT"

status_file="$PROJECT_ROOT/var/chinese/status/latest.json"
if [[ ! -f "$status_file" ]]; then
  echo "publish-chinese-report: missing $status_file" >&2
  exit 1
fi

report_date="$(python3 - "$status_file" <<'PY'
import json
import pathlib
import sys
print(json.loads(pathlib.Path(sys.argv[1]).read_text())["date"])
PY
)"
source_report="$PROJECT_ROOT/var/chinese/digests/$report_date.md"
if [[ ! -f "$source_report" ]]; then
  echo "publish-chinese-report: missing $source_report" >&2
  exit 1
fi

if git remote get-url origin >/dev/null 2>&1; then
  echo "Pulling latest changes..."
  git pull --rebase --autostash origin "$PUBLISH_BRANCH"
fi

mkdir -p chinese-reports
cp "$source_report" "chinese-reports/$report_date.md"
cp "$source_report" "chinese-reports/latest.md"

git add "chinese-reports/$report_date.md" chinese-reports/latest.md
if git diff --cached --quiet; then
  echo "publish-chinese-report: report is unchanged"
  exit 0
fi

git commit -m "Publish Chinese finance digest $report_date"
git push origin "HEAD:$PUBLISH_BRANCH"

echo "Published Chinese report for $report_date"
