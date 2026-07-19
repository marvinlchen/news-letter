#!/usr/bin/env bash
# Weekly forward A-share sector-leading-signal report.
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/finance-news-digest}"
REPORT_DIR="$PROJECT_ROOT/published/a-share-sector-radar-weekly"
STATUS_DIR="$PROJECT_ROOT/var/a-share-sector-radar-weekly-status"
CACHE_DIR="$PROJECT_ROOT/var/a-share-sector-radar-cache"
PUBLISH_ALLOWED=1
for arg in "$@"; do
  case "$arg" in
    --skip-ai|--no-news|--no-status)
      PUBLISH_ALLOWED=0
      ;;
  esac
done

mkdir -p "$REPORT_DIR" "$STATUS_DIR" "$CACHE_DIR" "$PROJECT_ROOT/var/log"

echo "=== 开始生成A股产业领先信号周报 ==="
echo "时间: $(date --iso-8601=seconds)"

python3 "$PROJECT_ROOT/scripts/a_share_sector_radar_weekly.py" \
  --project-root "$PROJECT_ROOT" \
  --config "$PROJECT_ROOT/config/a_share_sector_radar.json" \
  --output-dir "$REPORT_DIR" \
  --status-dir "$STATUS_DIR" \
  --cache-dir "$CACHE_DIR" \
  "$@"

echo "=== A股产业领先信号周报生成完成 ==="
echo "报告目录: $REPORT_DIR"

if [[ "${PUBLISH_TO_GITHUB:-1}" == "1" && "$PUBLISH_ALLOWED" == "1" ]]; then
  PUBLISH_REQUIRED="$(python3 - "$STATUS_DIR/latest-run.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit("publish gate: latest-run.json is missing")
status = json.loads(path.read_text(encoding="utf-8"))
publish_required = status.get("publish_required")
if not isinstance(publish_required, bool):
    raise SystemExit("publish gate: publish_required must be a boolean")
print("1" if publish_required else "0")
PY
)"
  if [[ "$PUBLISH_REQUIRED" == "1" ]]; then
    "$PROJECT_ROOT/scripts/publish-a-share-sector-radar-weekly.sh"
  else
    echo "本次运行无需发布：latest-run.json 的 publish_required=false"
  fi
elif [[ "$PUBLISH_ALLOWED" != "1" ]]; then
  echo "诊断参数已启用：强制跳过GitHub发布"
fi
