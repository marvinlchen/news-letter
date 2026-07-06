#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/home/ME/finance-news-digest}"
PUBLISH_BRANCH="${PUBLISH_BRANCH:-main}"
export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT"

LATEST_MD="$(ls -t published/sector-hotspots/*.md 2>/dev/null | grep -v latest | head -1)"
if [[ -z "$LATEST_MD" || ! -f "$LATEST_MD" ]]; then
  echo "publish-sector-hotspots: no report found in published/sector-hotspots/" >&2
  exit 1
fi

REPORT_DATE="$(basename "$LATEST_MD" .md)"
update_status_publish_commit() {
  local commit="$1"
  python3 - "$PROJECT_ROOT" "$REPORT_DATE" "$commit" <<'PY'
import json
import sys
from pathlib import Path

root, report_date, commit = sys.argv[1:4]
status_dir = Path(root) / "var" / "sector-hotspots-status"
for path in (status_dir / f"{report_date}.json", status_dir / "latest.json"):
    if not path.exists():
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    data["publish_commit"] = commit
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

cp "$LATEST_MD" "published/sector-hotspots/latest.md"

if git remote get-url origin >/dev/null 2>&1; then
  git pull --rebase --autostash origin "$PUBLISH_BRANCH"
fi

git add "published/sector-hotspots/${REPORT_DATE}.md" published/sector-hotspots/latest.md
if git diff --cached --quiet -- "published/sector-hotspots/${REPORT_DATE}.md" published/sector-hotspots/latest.md; then
  echo "publish-sector-hotspots: report is unchanged"
  update_status_publish_commit "$(git rev-parse HEAD)"
  exit 0
fi

git commit --only "published/sector-hotspots/${REPORT_DATE}.md" published/sector-hotspots/latest.md \
  -m "Publish sector hotspots ${REPORT_DATE}"
git push origin "HEAD:$PUBLISH_BRANCH"
update_status_publish_commit "$(git rev-parse HEAD)"
echo "Published sector hotspots report for $REPORT_DATE"
