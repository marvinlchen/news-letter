#!/usr/bin/env bash
# A股和美股板块热点分析 - 每日执行脚本
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

PROJECT_DIR="$HOME/finance-news-digest"
REPORTS_DIR="$PROJECT_DIR/published/sector-hotspots"
SCRIPT="$PROJECT_DIR/scripts/sector_hotspots.py"
CHECK_SCRIPT="$PROJECT_DIR/scripts/check_trading_day.py"

mkdir -p "$REPORTS_DIR"
mkdir -p "$PROJECT_DIR/var/log"

echo "=== 检查A股市场是否开盘 ==="
if ! python3 "$CHECK_SCRIPT"; then
    echo "今天A股不开盘（节假日或周末），跳过股票板块热点分析"
    exit 0
fi

echo "=== 开始生成股票板块热点分析 ==="
echo "时间: $(date)"

SECTOR_HOTSPOTS_AI_MODEL="${SECTOR_HOTSPOTS_AI_MODEL:-codebuddy}" \
SECTOR_HOTSPOTS_AI_MODEL_NAME="${SECTOR_HOTSPOTS_AI_MODEL_NAME:-deepseek-v4-pro}" \
  python3 "$SCRIPT" --output-dir "$REPORTS_DIR" --top "${SECTOR_HOTSPOTS_TOP:-8}"

echo "=== 股票板块热点分析完成 ==="
echo "报告保存在: $REPORTS_DIR"

if [[ "${PUBLISH_TO_GITHUB:-1}" == "1" ]]; then
  "$PROJECT_DIR/scripts/publish-sector-hotspots.sh"
fi
