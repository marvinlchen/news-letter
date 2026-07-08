#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/finance-news-digest}"
PUBLISH_BRANCH="${PUBLISH_BRANCH:-main}"
export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT"

DRY_RUN="${DRY_RUN:-0}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
LOG_FILE="$PROJECT_ROOT/var/log/archive-legacy.log"

mkdir -p "$PROJECT_ROOT/var/log"
exec 3>>"$LOG_FILE"
log() { echo "$(date "+%Y-%m-%d %H:%M:%S") $*" >&3; }

if [[ "$DRY_RUN" != "0" ]]; then
  log "=== DRY RUN: would archive reports older than $RETENTION_DAYS days ==="
else
  log "=== Archiving reports older than $RETENTION_DAYS days ==="
fi

cutoff="$(date -d "${RETENTION_DAYS} days ago" +%Y-%m-%d)"
log "Cutoff date: $cutoff (files dated strictly before this move to legacy/)"

if [[ "$DRY_RUN" == "0" ]]; then
  if git remote get-url origin >/dev/null 2>&1; then
    git pull --rebase --autostash origin "$PUBLISH_BRANCH" >>"$LOG_FILE" 2>&1 || log "WARN: git pull failed"
  fi
fi

moved=0
for d in published/*/; do
  [[ "$(basename "$d")" == "legacy" ]] && continue
  shopt -s nullglob
  for f in "$d"*.md; do
    base="$(basename "$f")"
    [[ "$base" == "latest.md" ]] && continue
    if [[ "$base" =~ ^([0-9]{4})-([0-9]{2})-([0-9]{2})\.md$ ]]; then
      fdate="${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
    else
      continue
    fi
    if [[ "$fdate" < "$cutoff" ]]; then
      dest_dir="${d}legacy"
      dest="$dest_dir/$base"
      if [[ -e "$dest" ]]; then
        log "SKIP (already in legacy): $f"
        continue
      fi
      if [[ "$DRY_RUN" != "0" ]]; then
        log "DRY RUN MOVE: $f -> $dest"
      else
        mkdir -p "$dest_dir"
        git mv "$f" "$dest"
        log "MOVED: $f -> $dest"
      fi
      moved=$((moved+1))
    fi
  done
  shopt -u nullglob
done

if [[ "$moved" -gt 0 && "$DRY_RUN" == "0" ]]; then
  if git diff --cached --quiet; then
    log "No staged changes to commit"
  else
    git commit -m "Archive $moved report(s) older than $RETENTION_DAYS days to legacy/" >>"$LOG_FILE" 2>&1
    git push origin "HEAD:$PUBLISH_BRANCH" >>"$LOG_FILE" 2>&1 && log "Pushed archive commit" || log "WARN: git push failed"
  fi
fi

log "Done. Moved this run: $moved"
echo "moved=$moved cutoff=$cutoff"
