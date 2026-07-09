#!/usr/bin/env bash
# 中证500涨跌分析 - 每日执行脚本
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

# 项目目录
PROJECT_DIR="$HOME/finance-news-digest"
REPORTS_DIR="$PROJECT_DIR/published/csi500"
SCRIPT="$PROJECT_DIR/scripts/index_analysis.py"
CHECK_SCRIPT="$PROJECT_DIR/scripts/check_trading_day.py"

# 创建报告目录
mkdir -p "$REPORTS_DIR"
mkdir -p "$PROJECT_DIR/var/log"

# 检查今天是否开盘
echo "=== 检查市场是否开盘 ==="
if ! python3 "$CHECK_SCRIPT"; then
    echo "今天不开盘（节假日或周末），跳过中证500分析"
    exit 0
fi

# 运行分析脚本
echo "=== 开始生成中证500涨跌分析 ==="
echo "时间: $(date)"

CSI500_AI_MODEL="${CSI500_AI_MODEL:-codebuddy}" \
CSI500_AI_MODEL_NAME="${CSI500_AI_MODEL_NAME:-hy3}" \
  python3 "$SCRIPT" --index csi500 --output-dir "$REPORTS_DIR" --top "${CSI500_TOP:-20}"

echo "=== 分析完成 ==="
echo "报告保存在: $REPORTS_DIR"

# Publish to GitHub
if [[ "${PUBLISH_TO_GITHUB:-1}" == "1" ]]; then
  "$PROJECT_DIR/scripts/publish-csi500.sh"
fi
