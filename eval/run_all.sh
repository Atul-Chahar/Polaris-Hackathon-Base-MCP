#!/bin/bash
# One-command harness: every local check, plus the speed test against a URL.
# Usage: eval/run_all.sh [URL]   (default: starts a local server on :8001)
set -uo pipefail
cd "$(dirname "$0")/.."
export LLM_PROVIDER=none
URL="${1:-}"
if [ -z "$URL" ]; then
  PORT=8001 .venv/bin/python server.py > /tmp/run_all_server.log 2>&1 &
  SERVER=$!
  trap 'kill $SERVER 2>/dev/null' EXIT
  until curl -sf localhost:8001/healthz > /dev/null; do sleep 1; done
  URL=http://127.0.0.1:8001/mcp
fi
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p eval/results NOTES
{
  echo "== unit";        .venv/bin/python -m unittest discover -s tests 2>&1 | tail -1
  echo "== smoke";       .venv/bin/python smoke_test.py "$URL"
  echo "== dev set";     .venv/bin/python eval/run_eval.py "$URL" --judge heuristic --out "eval/results/$STAMP.json" \
                           | grep -E "^(validity|ranking|unusual|irrelevant|mixed|recommendation|TOTAL|latency)"
  echo "== rec phrasing";   .venv/bin/python eval/rec_phrasing.py | grep TOTAL
  echo "== mixed phrasing"; .venv/bin/python eval/mixed_phrasing.py | grep TOTAL
  echo "== typos";          .venv/bin/python eval/typo_matrix.py | head -1
  echo "== synthetic";      .venv/bin/python eval/synth.py 400 | grep ALL
  echo "== speed";          .venv/bin/python eval/perf.py "$URL" --reps 1 | tail -2
} 2>&1 | tee "eval/results/$STAMP.txt"
echo "$STAMP $(git rev-parse --short HEAD) $(grep TOTAL "eval/results/$STAMP.txt" | head -1 | tr -s ' ')" >> NOTES/progress.md
