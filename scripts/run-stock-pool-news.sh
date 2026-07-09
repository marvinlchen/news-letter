#!/usr/bin/env bash
# 股票池重要新闻日报 - 每日执行脚本
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

# 项目目录
PROJECT_DIR="$HOME/finance-news-digest"
REPORTS_DIR="$PROJECT_DIR/published/stock-pool"

# 创建报告目录
mkdir -p "$REPORTS_DIR"
mkdir -p "$PROJECT_DIR/var/log"

# 运行生成脚本
echo "=== 开始生成股票池重要新闻日报 ==="
echo "时间: $(date)"

export PYTHONPATH="$PROJECT_DIR/src"
export STOCK_POOL_AI_MODEL_NAME="${STOCK_POOL_AI_MODEL_NAME:-hy3}"

python3 "$PROJECT_DIR/scripts/stock_pool_news.py" --output-dir "$REPORTS_DIR"

echo "=== 生成完成 ==="

# Publish to GitHub
if [[ "${PUBLISH_TO_GITHUB:-1}" == "1" ]]; then
  "$PROJECT_DIR/scripts/publish-stock-pool.sh"
fi
