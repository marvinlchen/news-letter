#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/home/ME/finance-news-digest}"
PUBLISH_BRANCH="${PUBLISH_BRANCH:-main}"
REPORT_DIR="${SECTOR_HOTSPOTS_REPORT_DIR:-published/sector-hotspots}"
STATUS_DIR="${SECTOR_HOTSPOTS_STATUS_DIR:-var/sector-hotspots-status}"
COMMIT_LABEL="${SECTOR_HOTSPOTS_COMMIT_LABEL:-sector hotspots}"
PUBLISH_NAME="${SECTOR_HOTSPOTS_PUBLISH_NAME:-sector-hotspots}"
export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT"

LATEST_MD="$(ls -t "$REPORT_DIR"/*.md 2>/dev/null | grep -v latest | head -1)"
if [[ -z "$LATEST_MD" || ! -f "$LATEST_MD" ]]; then
  echo "publish-${PUBLISH_NAME}: no report found in ${REPORT_DIR}/" >&2
  exit 1
fi

REPORT_DATE="$(basename "$LATEST_MD" .md)"
update_status_publish_commit() {
  local commit="$1"
  python3 - "$PROJECT_ROOT" "$STATUS_DIR" "$REPORT_DATE" "$commit" <<'PY'
import json
import sys
from pathlib import Path

root, status_dir_name, report_date, commit = sys.argv[1:5]
status_dir = Path(root) / status_dir_name
for path in (status_dir / f"{report_date}.json", status_dir / "latest.json"):
    if not path.exists():
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    data["publish_commit"] = commit
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

cp "$LATEST_MD" "${REPORT_DIR}/latest.md"

if git remote get-url origin >/dev/null 2>&1; then
  git pull --rebase --autostash origin "$PUBLISH_BRANCH"
fi

git add "${REPORT_DIR}/${REPORT_DATE}.md" "${REPORT_DIR}/latest.md"
if git diff --cached --quiet -- "${REPORT_DIR}/${REPORT_DATE}.md" "${REPORT_DIR}/latest.md"; then
  echo "publish-${PUBLISH_NAME}: report is unchanged"
  update_status_publish_commit "$(git rev-parse HEAD)"
  exit 0
fi

git commit --only "${REPORT_DIR}/${REPORT_DATE}.md" "${REPORT_DIR}/latest.md" \
  -m "Publish ${COMMIT_LABEL} ${REPORT_DATE}"
git push origin "HEAD:$PUBLISH_BRANCH"
update_status_publish_commit "$(git rev-parse HEAD)"
echo "Published ${PUBLISH_NAME} report for $REPORT_DATE"
