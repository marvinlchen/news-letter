#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/finance-news-digest}"
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$PROJECT_ROOT/src"
export CODEX_BIN="${CODEX_BIN:-codebuddy}"
# 模型留空 = 使用 CodeBuddy 全局模型（~/.codebuddy/settings.json 的 model）
export CODEX_MODEL="${CODEX_MODEL:-}"
export CODEX_HOME="${CODEX_HOME:-$HOME/.codebuddy}"

# text 输出：stdout 只含模型回复，避免 CodeBuddy stdout ~64KB 截断（json 会先回显整个 prompt，大 prompt 就会截断在多字节字符中间）
export CODEX_OUTPUT_FORMAT="${CODEX_OUTPUT_FORMAT:-text}"

REDDIT_ENV_FILE="${REDDIT_ENV_FILE:-$HOME/.config/finance-news-digest/reddit.env}"
if [[ -f "$REDDIT_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$REDDIT_ENV_FILE"
  set +a
fi

if [[ -z "${REDDIT_CLIENT_ID:-}" || -z "${REDDIT_CLIENT_SECRET:-}" ]]; then
  echo "[ERROR] Reddit digest disabled: REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are required; anonymous RSS is no longer usable." >&2
  exit 4
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
