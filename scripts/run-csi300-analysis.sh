#!/usr/bin/env bash
# 沪深300涨跌分析 - 每日执行脚本
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

# 项目目录
PROJECT_DIR="$HOME/finance-news-digest"
REPORTS_DIR="$PROJECT_DIR/published/csi300"
SCRIPT="$PROJECT_DIR/scripts/csi300_analysis.py"
CHECK_SCRIPT="$PROJECT_DIR/scripts/check_trading_day.py"

# 创建报告目录
mkdir -p "$REPORTS_DIR"
mkdir -p "$PROJECT_DIR/var/log"

# 检查今天是否开盘
echo "=== 检查市场是否开盘 ==="
if ! python3 "$CHECK_SCRIPT"; then
    echo "今天不开盘（节假日或周末），跳过沪深300分析"
    exit 0
fi

# 运行分析脚本
echo "=== 开始生成沪深300涨跌分析 ==="
echo "时间: $(date)"

CSI300_AI_MODEL="${CSI300_AI_MODEL:-codebuddy}" \
CSI300_AI_MODEL_NAME="${CSI300_AI_MODEL_NAME:-deepseek-v4-pro}"
  python3 "$SCRIPT" --output-dir "$REPORTS_DIR" --top "${CSI300_TOP:-20}"

echo "=== 分析完成 ==="
echo "报告保存在: $REPORTS_DIR"

# Publish to GitHub
if [[ "${PUBLISH_TO_GITHUB:-1}" == "1" ]]; then
  "$PROJECT_DIR/scripts/publish-csi300.sh"
fi
