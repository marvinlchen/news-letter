#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/finance-news-digest}"
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$PROJECT_ROOT/src"
export CODEX_BIN="${CODEX_BIN:-codebuddy}"
export CODEX_HOME="${CODEX_HOME:-$HOME/.codebuddy}"

args=(
  --project-root "$PROJECT_ROOT"
  --output-root "$PROJECT_ROOT/var"
  --use-codex
)
if [[ "${CODEX_REQUIRED:-0}" == "1" ]]; then
  args+=(--require-codex)
fi

set +e
python3 -m finance_digest.deep_reads "${args[@]}"
report_rc=$?
set -e

if [[ "$report_rc" == "0" && "${PUBLISH_TO_GITHUB:-1}" == "1" ]]; then
  "$PROJECT_ROOT/scripts/publish-deep-reads.sh"
fi

exit "$report_rc"
