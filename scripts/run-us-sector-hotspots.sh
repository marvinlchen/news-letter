#!/usr/bin/env bash
# 美股板块热点分析 - 美股收盘后执行脚本
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

PROJECT_DIR="$HOME/finance-news-digest"
REPORTS_DIR="$PROJECT_DIR/published/us-sector-hotspots"
SCRIPT="$PROJECT_DIR/scripts/sector_hotspots.py"

mkdir -p "$REPORTS_DIR"
mkdir -p "$PROJECT_DIR/var/log"

echo "=== 开始生成美股板块热点分析 ==="
echo "时间: $(date)"

SECTOR_HOTSPOTS_AI_MODEL="${SECTOR_HOTSPOTS_AI_MODEL:-codebuddy}" \
SECTOR_HOTSPOTS_AI_MODEL_NAME="${SECTOR_HOTSPOTS_AI_MODEL_NAME:-hy3}" \
US_SECTOR_HOTSPOTS_TOP="${US_SECTOR_HOTSPOTS_TOP:-30}" \
US_SECTOR_HOTSPOTS_STOCK_LIMIT="${US_SECTOR_HOTSPOTS_STOCK_LIMIT:-6}" \
US_SECTOR_HOTSPOTS_CONFIG="${US_SECTOR_HOTSPOTS_CONFIG:-$PROJECT_DIR/config/us_sector_hotspots.json}" \
  python3 "$SCRIPT" --market us --output-dir "$REPORTS_DIR" --status-dir-name us-sector-hotspots-status --top "${US_SECTOR_HOTSPOTS_TOP:-30}"

echo "=== 美股板块热点分析完成 ==="
echo "报告保存在: $REPORTS_DIR"

if [[ "${PUBLISH_TO_GITHUB:-1}" == "1" ]]; then
  "$PROJECT_DIR/scripts/publish-us-sector-hotspots.sh"
fi
