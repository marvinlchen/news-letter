#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/finance-news-digest}"
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$PROJECT_ROOT/src"
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex-finance}"

args=(
  run
  --project-root "$PROJECT_ROOT"
  --output-root "$PROJECT_ROOT/var"
  --use-codex
)
if [[ "${CODEX_REQUIRED:-0}" == "1" ]]; then
  args+=(--require-codex)
fi

exec python3 -m finance_digest "${args[@]}"
