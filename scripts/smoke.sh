#!/usr/bin/env bash
set -uo pipefail

URL="http://localhost:8000/health"
STARTED_SERVER=0
SERVER_PID=""

status_of() {
  curl -s -o /dev/null -w "%{http_code}" "$URL" 2>/dev/null
}

if [ "$(status_of)" != "200" ]; then
  uv run uvicorn src.api.app:app --port 8000 >/tmp/specpilot-smoke.log 2>&1 &
  SERVER_PID=$!
  STARTED_SERVER=1
  for _ in $(seq 1 30); do
    [ "$(status_of)" = "200" ] && break
    sleep 0.5
  done
fi

if [ "$(status_of)" = "200" ]; then
  echo "OK smoke"
  RESULT=0
else
  echo "FAIL smoke"
  RESULT=1
fi

if [ "$STARTED_SERVER" = "1" ]; then
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
fi

exit "$RESULT"
