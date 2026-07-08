#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/finance-news-digest}"
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$PROJECT_ROOT/src"
export CODEX_BIN="${CODEX_BIN:-codebuddy}"
export CODEX_MODEL="${CODEX_MODEL:-hy3-preview-agent}"
export CODEX_HOME="${CODEX_HOME:-$HOME/.codebuddy}"

REDDIT_ENV_FILE="${REDDIT_ENV_FILE:-$HOME/.config/finance-news-digest/reddit.env}"
if [[ -f "$REDDIT_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$REDDIT_ENV_FILE"
  set +a
fi

args=(
  --project-root "$PROJECT_ROOT"
  --output-root "$PROJECT_ROOT/var"
  --use-codex
)
if [[ "${REDDIT_CODEX_REQUIRED:-1}" == "1" ]]; then
  args+=(--require-codex)
fi

set +e
python3 -m finance_digest.reddit_digest "${args[@]}"
report_rc=$?
set -e

if [[ "$report_rc" == "0" && "${PUBLISH_TO_GITHUB:-1}" == "1" ]]; then
  "$PROJECT_ROOT/scripts/publish-reddit-report.sh"
fi

exit "$report_rc"
