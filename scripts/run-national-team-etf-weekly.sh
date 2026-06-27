#!/usr/bin/env bash
# Weekly broad-index ETF share-flow report.
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/finance-news-digest}"
REPORTS_DIR="$PROJECT_ROOT/published/national-team-etf"
SCRIPT="$PROJECT_ROOT/scripts/national_team_etf_weekly.py"

mkdir -p "$REPORTS_DIR" "$PROJECT_ROOT/var/log"

echo "=== 开始生成国家队ETF观察周报 ==="
echo "时间: $(date --iso-8601=seconds)"

python3 "$SCRIPT" --project-root "$PROJECT_ROOT" --output-dir "$REPORTS_DIR" "$@"

echo "=== 国家队ETF观察周报生成完成 ==="
echo "报告目录: $REPORTS_DIR"

if [[ "${PUBLISH_TO_GITHUB:-1}" == "1" ]]; then
  "$PROJECT_ROOT/scripts/publish-national-team-etf-weekly.sh"
fi
