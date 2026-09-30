#!/usr/bin/env bash
# Weekly all-market investment review (A-share + US + stock pool).
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/finance-news-digest}"
REPORT_DIR="$PROJECT_ROOT/published/weekly-review"
STATUS_DIR="$PROJECT_ROOT/var/weekly-review-status"
PUBLISH_ALLOWED=1
for arg in "$@"; do
  case "$arg" in
    --skip-ai|--no-status|--no-news)
      PUBLISH_ALLOWED=0
      ;;
  esac
done

mkdir -p "$REPORT_DIR" "$STATUS_DIR" "$PROJECT_ROOT/var/log"

echo "=== 开始生成每周投资总结 ==="
echo "时间: $(date --iso-8601=seconds)"

python3 "$PROJECT_ROOT/scripts/weekly_review.py" \
  --project-root "$PROJECT_ROOT" \
  --output-dir "$REPORT_DIR" \
  --status-dir "$STATUS_DIR" \
  "$@"

echo "=== 每周投资总结生成完成 ==="
echo "报告目录: $REPORT_DIR"

if [[ "${PUBLISH_TO_GITHUB:-1}" == "1" && "$PUBLISH_ALLOWED" == "1" ]]; then
  "$PROJECT_ROOT/scripts/publish-weekly-review.sh"
else
  echo "发布已跳过（PUBLISH_TO_GITHUB=0 或诊断模式）"
fi
