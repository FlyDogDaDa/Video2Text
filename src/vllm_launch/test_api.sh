#!/usr/bin/env bash
# Quick curl test + speed measurement for the vLLM API

PORT="${PORT:-8746}"
URL="http://localhost:${PORT}/v1/chat/completions"

echo "Testing vLLM API at ${URL} ..."
echo ""

# Time the request
START=$(date +%s%N)

RESPONSE=$(curl -s -w "\n%{http_code}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-4-12B-it-qat-w4a16-ct",
    "messages": [{"role": "user", "content": "One word answer: hello"}],
    "max_tokens": 32,
    "temperature": 0
  }' \
  "${URL}")

END=$(date +%s%N)

# Extract status code and body
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

# Calculate elapsed time in ms
ELAPSED=$(( (END - START) / 1000000 ))

echo "Status: ${HTTP_CODE}"
echo "Time: ${ELAPSED} ms"
echo ""
echo "Response:"
echo "${BODY}" | python -m json.tool 2>/dev/null || echo "${BODY}"
echo ""

# Parse output speed from response
if echo "${BODY}" | python3 -c "
import json, sys
data = json.load(sys.stdin)
tokens = data['usage']['completion_tokens']
print(f'TPS: {tokens / ({ELAPSED} / 1000):.2f} tok/s')
" 2>/dev/null; then
  :
else
  echo "(could not parse TPS from response)"
fi
