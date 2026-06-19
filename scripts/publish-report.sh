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

# 检查是否存在当日的沪深300分析，如果存在则合并到日报开头
csi300_report="$PROJECT_ROOT/published/csi300/$report_date.md"
combined_report="$PROJECT_ROOT/var/digests/${report_date}_combined.md"

if [[ -f "$csi300_report" ]]; then
  echo "publish-report: 找到沪深300分析，合并到日报开头..."
  # 合并：先写沪深300分析，再写日报内容
  {
    cat "$csi300_report"
    echo ""
    echo "---"
    echo ""
    cat "$source_report"
  } > "$combined_report"
  source_report="$combined_report"
  echo "publish-report: 已合并沪深300分析"
else
  echo "publish-report: 未找到沪深300分析 ($csi300_report)，仅发布日报"
fi

if git remote get-url origin >/dev/null 2>&1; then
  git pull --rebase --autostash origin "$PUBLISH_BRANCH"
fi

mkdir -p published/daily
cp "$source_report" "published/daily/$report_date.md"
cp "$source_report" "published/daily/latest.md"

git add "published/daily/$report_date.md" published/daily/latest.md
if git diff --cached --quiet; then
  echo "publish-report: report is unchanged"
  exit 0
fi

git commit -m "Publish finance digest $report_date"
git push origin "HEAD:$PUBLISH_BRANCH"
