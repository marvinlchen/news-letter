#!/usr/bin/env bash
# 中证1000涨跌分析 - 每日执行脚本
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

# 项目目录
PROJECT_DIR="$HOME/finance-news-digest"
REPORTS_DIR="$PROJECT_DIR/published/csi1000"
SCRIPT="$PROJECT_DIR/scripts/index_analysis.py"
CHECK_SCRIPT="$PROJECT_DIR/scripts/check_trading_day.py"

# 创建报告目录
mkdir -p "$REPORTS_DIR"
mkdir -p "$PROJECT_DIR/var/log"

# 检查今天是否开盘
echo "=== 检查市场是否开盘 ==="
if ! python3 "$CHECK_SCRIPT"; then
    echo "今天不开盘（节假日或周末），跳过中证1000分析"
    exit 0
fi

# 运行分析脚本
echo "=== 开始生成中证1000涨跌分析 ==="
echo "时间: $(date)"

CSI1000_AI_MODEL="${CSI1000_AI_MODEL:-codebuddy}" \
CSI1000_AI_MODEL_NAME="${CSI1000_AI_MODEL_NAME:-hy3}" \
  python3 "$SCRIPT" --index csi1000 --output-dir "$REPORTS_DIR" --top "${CSI1000_TOP:-20}"

echo "=== 分析完成 ==="
echo "报告保存在: $REPORTS_DIR"

# Publish to GitHub
if [[ "${PUBLISH_TO_GITHUB:-1}" == "1" ]]; then
  "$PROJECT_DIR/scripts/publish-csi1000.sh"
fi
