#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/home/ME/finance-news-digest}"
PUBLISH_BRANCH="${PUBLISH_BRANCH:-main}"
REPORT_DIR="published/a-share-sector-radar-weekly"
STATUS_DIR="var/a-share-sector-radar-weekly-status"
ARTIFACT_STATUS_NAME="latest-artifact.json"
RUN_STATUS_NAME="latest-run.json"
export PATH="$HOME/.local/bin:$PATH"

if command -v flock >/dev/null 2>&1 && [[ "${A_SHARE_RADAR_GIT_LOCK_HELD:-0}" != "1" ]]; then
  mkdir -p "$PROJECT_ROOT/var"
  exec /usr/bin/flock -w 300 "$PROJECT_ROOT/var/git-publish.lock" \
    env A_SHARE_RADAR_GIT_LOCK_HELD=1 PROJECT_ROOT="$PROJECT_ROOT" PUBLISH_BRANCH="$PUBLISH_BRANCH" "$0" "$@"
fi

cd "$PROJECT_ROOT"
REPORT_DATE=""

update_publish_status() {
  local publish_status="$1"
  local commit="${2:-}"
  local error="${3:-}"
  [[ -n "$REPORT_DATE" ]] || return 0
  python3 - "$PROJECT_ROOT" "$STATUS_DIR" "$REPORT_DATE" "$publish_status" "$commit" "$error" "$ARTIFACT_STATUS_NAME" "$RUN_STATUS_NAME" <<'PY'
import json
import sys
from pathlib import Path

(
    root,
    status_dir_name,
    report_date,
    publish_status,
    commit,
    error,
    artifact_status_name,
    run_status_name,
) = sys.argv[1:9]
status_dir = Path(root) / status_dir_name

paths = [status_dir / f"{report_date}.json", status_dir / artifact_status_name]
run_path = status_dir / run_status_name
if run_path.exists():
    run_data = json.loads(run_path.read_text(encoding="utf-8"))
    run_artifact_date = str(run_data.get("artifact_date") or run_data.get("date") or "")
    if run_artifact_date == report_date:
        paths.append(run_path)

for path in paths:
    if not path.exists():
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    data["publish_status"] = publish_status
    data["publish_commit"] = commit
    data["publish_error"] = error[:1000]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

on_error() {
  local exit_code=$?
  trap - ERR
  update_publish_status "publish_failed" "" "publisher exited with code ${exit_code}"
  exit "$exit_code"
}
trap on_error ERR

REPORT_DATE="$(python3 - "$PROJECT_ROOT" "$REPORT_DIR" "$STATUS_DIR" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
report_dir = root / sys.argv[2]
status_path = root / sys.argv[3] / "latest-artifact.json"
if not status_path.is_file():
    raise SystemExit("publish: latest artifact status is missing")
status = json.loads(status_path.read_text(encoding="utf-8"))
report_date = str(status.get("date", ""))
if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", report_date):
    raise SystemExit("publish: invalid status date")
if not status.get("publishable") or status.get("fallback_used") or status.get("codex_error") or status.get("error"):
    raise SystemExit("publish: status is not publishable")
if status.get("mode") == "rules-diagnostic":
    raise SystemExit("publish: diagnostic report is forbidden")

report = report_dir / f"{report_date}.md"
latest = report_dir / "latest.md"
ledger = report_dir / "ledger.json"
snapshot = report_dir / "snapshots" / f"{report_date}.json"
expected_output = str(report.resolve())
if str(Path(status.get("output_path", "")).resolve()) != expected_output:
    raise SystemExit("publish: output_path does not match status date")

def digest(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"publish: missing artifact {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()

checks = (
    (report, "report_sha256"),
    (ledger, "ledger_sha256"),
    (snapshot, "snapshot_sha256"),
)
for path, key in checks:
    if digest(path) != status.get(key):
        raise SystemExit(f"publish: {key} mismatch")
if report.read_bytes() != latest.read_bytes():
    raise SystemExit("publish: latest.md differs from dated report")
print(report_date)
PY
)"

SNAPSHOT_PATH="$REPORT_DIR/snapshots/$REPORT_DATE.json"

if git remote get-url origin >/dev/null 2>&1; then
  git fetch origin "$PUBLISH_BRANCH"
  REMOTE_REF="$(git rev-parse "origin/$PUBLISH_BRANCH")"
  LOCAL_REF="$(git rev-parse HEAD)"
  if [[ "$LOCAL_REF" != "$REMOTE_REF" ]] && git merge-base --is-ancestor "$LOCAL_REF" "$REMOTE_REF"; then
    git merge --ff-only "$REMOTE_REF"
  elif [[ "$LOCAL_REF" != "$REMOTE_REF" ]] && ! git merge-base --is-ancestor "$REMOTE_REF" "$LOCAL_REF"; then
    echo "publish: local and origin/$PUBLISH_BRANCH have diverged" >&2
    exit 1
  fi
fi

ARTIFACT_PATHS=(
  "$REPORT_DIR/$REPORT_DATE.md"
  "$REPORT_DIR/latest.md"
  "$REPORT_DIR/ledger.json"
  "$SNAPSHOT_PATH"
)

git add -- "${ARTIFACT_PATHS[@]}"
CREATED_COMMIT=0
if ! git diff --cached --quiet -- "${ARTIFACT_PATHS[@]}"; then
  git commit --only \
    -m "Publish A-share sector radar weekly $REPORT_DATE" \
    -m "Co-authored-by: Codex <noreply@openai.com>" \
    -- "${ARTIFACT_PATHS[@]}"
  CREATED_COMMIT=1
fi

COMMIT="$(git log -1 --format=%H -- "$REPORT_DIR/$REPORT_DATE.md")"
if [[ -z "$COMMIT" ]]; then
  echo "publish: cannot resolve the report's Git commit" >&2
  exit 1
fi

if [[ "$CREATED_COMMIT" == "1" ]]; then
  git push origin "HEAD:$PUBLISH_BRANCH"
elif git remote get-url origin >/dev/null 2>&1 && ! git merge-base --is-ancestor "$COMMIT" "origin/$PUBLISH_BRANCH"; then
  # A previous push may have failed after the artifact commit was created.
  git push origin "HEAD:$PUBLISH_BRANCH"
fi

update_publish_status "published" "$COMMIT" ""
trap - ERR
if [[ "$CREATED_COMMIT" == "1" ]]; then
  echo "Published A-share sector radar weekly report for $REPORT_DATE at $COMMIT"
else
  echo "A-share sector radar weekly report for $REPORT_DATE is unchanged; existing commit: $COMMIT"
fi
