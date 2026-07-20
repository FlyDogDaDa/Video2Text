#!/usr/bin/env bash
# block_me_with_file.sh
#
# PURPOSE
#   Block the current shell until a log file reaches a success condition
#   or an error condition.  Used as a lightweight healthcheck before
#   sending API calls to vLLM / other long-startup services.
#
# USAGE
#   bash src/vllm_launch/block_me_with_file.sh [LOG_FILE] [INTERVAL_S] [SUCCESS_PAT] [ERROR_PAT]
#
#   Arguments (all optional):
#     LOG_FILE        Path to the log file to poll.  Default: vllm.log
#     INTERVAL_S      Seconds between polls.  Default: 30
#     SUCCESS_PAT     Grepped pattern that means "ready".  Default: "Application startup complete."
#     ERROR_PAT       Grepped pattern that means "fail" (case-insensitive).  Default: "error"
#
# EXAMPLES
#   # Block until vLLM finishes starting (default args):
#   bash src/vllm_launch/block_me_with_file.sh
#
#   # Custom log, 60s interval:
#   bash src/vllm_launch/block_me_with_file.sh server.log 60 "READY" "FATAL"

FILE="${1:-vllm.log}"
INTERVAL="${2:-30}"                    # seconds between checks
SUCCESS_PATTERN="${3:-Application startup complete.}"
ERROR_PATTERN="${4:-error}"

echo "Polling ${FILE} every ${INTERVAL}s"
echo "  Success pattern : ${SUCCESS_PATTERN}"
echo "  Error pattern   : ${ERROR_PATTERN}"
echo ""

while true; do
  if ! [ -f "${FILE}" ]; then
    echo "[${SECONDS}s] ${FILE} not found — waiting..."
    sleep "${INTERVAL}"
    continue
  fi

  if grep -qi "${ERROR_PATTERN}" "${FILE}" 2>/dev/null; then
    echo "❌ Error detected in ${FILE}:"
    grep -i "${ERROR_PATTERN}" "${FILE}" | tail -5
    exit 1
  fi

  if grep -q "${SUCCESS_PATTERN}" "${FILE}" 2>/dev/null; then
    echo "✅ ${SUCCESS_PATTERN}"
    exit 0
  fi

  # Also check if file has grown (shows something is happening)
  LINES=$(wc -l < "${FILE}" 2>/dev/null || echo 0)
  echo "[${SECONDS}s] Waiting... (${LINES} lines so far)"
  sleep "${INTERVAL}"
done
