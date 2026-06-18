#!/usr/bin/env bash
# 沪深300涨跌分析 - 每日执行脚本
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

# 项目目录
PROJECT_DIR="$HOME/finance-news-digest"
REPORTS_DIR="$PROJECT_DIR/published/csi300"
SCRIPT="$PROJECT_DIR/scripts/csi300_analysis.py"

# 创建报告目录
mkdir -p "$REPORTS_DIR"
mkdir -p "$PROJECT_DIR/var/log"

# 运行分析脚本
echo "=== 开始生成沪深300涨跌分析 ==="
echo "时间: $(date)"

python3 "$SCRIPT" --output-dir "$REPORTS_DIR" --top "${CSI300_TOP:-20}"

echo "=== 分析完成 ==="
echo "报告保存在: $REPORTS_DIR"

# Publish to GitHub
if [[ "${PUBLISH_TO_GITHUB:-1}" == "1" ]]; then
  "$PROJECT_DIR/scripts/publish-csi300.sh"
fi
