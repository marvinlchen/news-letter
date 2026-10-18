#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
PROJECT_ROOT="${PROJECT_ROOT:-$HOME/finance-news-digest}"
PUBLISH_BRANCH="${PUBLISH_BRANCH:-main}"
if [[ "${ANNOUNCEMENTS_PUBLISH_LOCK_HELD:-0}" != 1 ]]; then
  exec /usr/bin/flock -w 120 "$PROJECT_ROOT/var/git-publish.lock" env ANNOUNCEMENTS_PUBLISH_LOCK_HELD=1 PROJECT_ROOT="$PROJECT_ROOT" PUBLISH_BRANCH="$PUBLISH_BRANCH" "$0" "$@"
fi
cd "$PROJECT_ROOT"
STATUS_PATH="$PROJECT_ROOT/var/a-share-announcements-status/latest-artifact.json"
mapfile -t artifacts < <(python3 - "$STATUS_PATH" "$PROJECT_ROOT" <<'PY'
import hashlib,json,re,sys
from pathlib import Path
s=json.load(open(sys.argv[1])); root=Path(sys.argv[2]).resolve(); folder=root/'published/a-share-announcements'
if (s.get('output_format')!='markdown' or not s.get('publishable') or s.get('diagnostic') or s.get('error') or s.get('fallback_used')
    or not s.get('fact_review',{}).get('passed') or not s.get('markdown_review',{}).get('passed')):
 raise SystemExit('publish gate: Markdown did not pass fact and content audits')
date=s.get('date','')
if not re.fullmatch(r'20\d{2}-\d{2}-\d{2}',date): raise SystemExit('invalid report date')
md=Path(s['output_path']).resolve(); expected_md=folder/(date+'.md'); expected_json=folder/(date+'.json')
if (md!=expected_md or s.get('report_filename')!=date+'.md'
    or Path(s.get('markdown_path','')).resolve()!=expected_md
    or Path(s.get('json_path','')).resolve()!=expected_json):
 raise SystemExit('Markdown/JSON path mismatch')
for artifact in [expected_md,folder/'latest.md',expected_json]:
 if not artifact.is_file() or artifact.resolve()!=artifact: raise SystemExit('missing or redirected artifact')
md_hash=hashlib.sha256(md.read_bytes()).hexdigest()
if md_hash!=s.get('report_sha256') or md_hash!=s.get('markdown_sha256'): raise SystemExit('Markdown hash mismatch')
if hashlib.sha256(expected_json.read_bytes()).hexdigest()!=s.get('json_sha256'): raise SystemExit('JSON hash mismatch')
if (folder/'latest.md').read_bytes()!=md.read_bytes(): raise SystemExit('latest Markdown differs')
for p in [md,folder/'latest.md',expected_json]:
 print(p.relative_to(root))
print(date)
PY
)
# Process substitution does not propagate Python failure; require all four returned lines.
if [[ "${#artifacts[@]}" != 4 ]]; then
  echo 'publish gate failed' >&2
  exit 2
fi
REPORT_DATE="${artifacts[3]}"
ARTIFACT_PATHS=("${artifacts[@]:0:3}")
[[ "$(git branch --show-current)" == "$PUBLISH_BRANCH" ]] || { echo 'publish: wrong branch' >&2; exit 2; }
export GIT_SSH_COMMAND='ssh -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=2'
git fetch origin "$PUBLISH_BRANCH"
if git merge-base --is-ancestor HEAD "origin/$PUBLISH_BRANCH"; then
  git merge --ff-only "origin/$PUBLISH_BRANCH"
elif git merge-base --is-ancestor "origin/$PUBLISH_BRANCH" HEAD; then
  # Only retry this report's own pending commit; never ship unrelated local commits.
  while IFS= read -r subject; do
    [[ "$subject" == "Publish A-share major announcements $REPORT_DATE" ]] || { echo 'publish: unrelated local commits pending' >&2; exit 2; }
  done < <(git log --format=%s "origin/$PUBLISH_BRANCH..HEAD")
else
  echo 'publish: local branch diverged' >&2
  exit 2
fi
git add -- "${ARTIFACT_PATHS[@]}"
if ! git diff --cached --quiet -- "${ARTIFACT_PATHS[@]}"; then
  git commit --only -m "Publish A-share major announcements $REPORT_DATE" -m 'Co-authored-by: Codex <noreply@openai.com>' -- "${ARTIFACT_PATHS[@]}"
fi
git push origin "HEAD:$PUBLISH_BRANCH"
python3 - "$PROJECT_ROOT/var/a-share-announcements-status" "$REPORT_DATE" "$(git rev-parse HEAD)" <<'PY'
import json,sys
from pathlib import Path
folder=Path(sys.argv[1])
for name in ['latest-run.json','latest-artifact.json',sys.argv[2]+'.json']:
 p=folder/name
 if p.exists():
  s=json.loads(p.read_text())
  if s.get('date')==sys.argv[2]:
   s.update(publish_status='published',publish_commit=sys.argv[3],publish_error='')
   p.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
PY
