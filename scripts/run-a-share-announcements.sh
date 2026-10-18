#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
export TZ=Asia/Shanghai
PROJECT_ROOT="${PROJECT_ROOT:-$HOME/finance-news-digest}"
export CODEBUDDY_BIN="${CODEBUDDY_BIN:-codebuddy}"
export ANNOUNCEMENTS_AI_MODEL="${ANNOUNCEMENTS_AI_MODEL:-}"
STATUS_DIR="$PROJECT_ROOT/var/a-share-announcements-status"
PYTHON="${ANNOUNCEMENTS_PYTHON:-$PROJECT_ROOT/var/a-share-announcements-venv/bin/python}"
mkdir -p "$PROJECT_ROOT/var/log" "$STATUS_DIR"
cd "$PROJECT_ROOT"
echo "=== A股重大公告日报 $(date --iso-8601=seconds) ==="
# A 55-minute budget leaves time before 06:00; failures remain visible in status/log.
if /usr/bin/timeout --signal=TERM --kill-after=15s 3300s "$PYTHON" "$PROJECT_ROOT/scripts/a_share_announcements.py" --project-root "$PROJECT_ROOT" "$@"; then
  :
else
  result=$?
  if [[ "$result" == 124 || "$result" == 137 ]]; then
    python3 - "$STATUS_DIR/latest-run.json" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1])
d=json.loads(p.read_text()) if p.exists() else {}
d.update(state='failed',publishable=False,publish_required=False,error='运行超过55分钟预算，未发布；请检查日志及数据源',publish_status='not_published')
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
PY
  fi
  exit "$result"
fi
publish_allowed=1
for arg in "$@"; do
  case "$arg" in
    --limit|--limit=*|--collect-only|--output-dir|--output-dir=*|--status-dir|--status-dir=*) publish_allowed=0 ;;
  esac
done
if [[ "${PUBLISH_TO_GITHUB:-1}" == 1 && "$publish_allowed" == 1 ]]; then
  publish_required="$(python3 - "$STATUS_DIR/latest-run.json" <<'PY'
import json,sys
s=json.load(open(sys.argv[1]))
print('1' if s.get('publish_required') is True and s.get('publishable') is True and not s.get('diagnostic') else '0')
PY
)"
  if [[ "$publish_required" == 1 ]]; then
    if /usr/bin/timeout --signal=TERM --kill-after=10s 150s "$PROJECT_ROOT/scripts/publish-a-share-announcements.sh"; then
      :
    else
      publish_result=$?
      python3 - "$STATUS_DIR" "$publish_result" <<'PYSTATUS'
import json,sys
from pathlib import Path
folder=Path(sys.argv[1])
latest=folder/'latest-artifact.json'
if latest.exists():
 original=json.loads(latest.read_text()); date=original.get('date')
 for name in ['latest-artifact.json','latest-run.json',str(date)+'.json']:
  p=folder/name
  if p.exists():
   s=json.loads(p.read_text())
   if s.get('date')==date:
    s.update(publish_status='publish_failed',publish_error='发布失败或超时，返回码'+sys.argv[2])
    p.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
PYSTATUS
      exit "$publish_result"
    fi
  fi
fi
