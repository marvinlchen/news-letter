#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/finance-news-digest}"
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$PROJECT_ROOT/src"
export CODEX_BIN="${CODEX_BIN:-codex}"
export CODEX_HOME="${CODEX_HOME:-$HOME/.codebuddy}"

# Use a separate output root for Chinese reports
CHINESE_OUTPUT_ROOT="$PROJECT_ROOT/var/chinese"

args=(
  run
  --project-root "$PROJECT_ROOT"
  --output-root "$CHINESE_OUTPUT_ROOT"
  --sources-file "$PROJECT_ROOT/config/chinese_sources.json"
  --use-codex
)
if [[ "${CODEX_REQUIRED:-0}" == "1" ]]; then
  args+=(--require-codex)
fi

set +e
python3 -m finance_digest "${args[@]}"
digest_rc=$?
set -e

if [[ "$digest_rc" == "0" && "${PUBLISH_TO_GITHUB:-1}" == "1" ]]; then
  "$PROJECT_ROOT/scripts/publish-chinese-report.sh"
fi

exit "$digest_rc"
