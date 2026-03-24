#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
SERIAL_PORT="${SERIAL_PORT:-/dev/ttyACM0}"
BAUD="${BAUD:-115200}"
REFRESH_INTERVAL="${REFRESH_INTERVAL:-5}"
DB_PATH="${DB_PATH:-data/telemetry.db}"
DASHBOARD_PATH="${DASHBOARD_PATH:-data/dashboard_live.html}"

RUNTIME_DIR="${RUNTIME_DIR:-/tmp/cubesat_live_demo}"
LOGGER_LOG="$RUNTIME_DIR/logger.log"
SERVER_LOG="$RUNTIME_DIR/server.log"

mkdir -p "$RUNTIME_DIR"

LOGGER_PID=""
SERVER_PID=""

cleanup() {
  echo
  echo "[demo] Stopping live demo..."
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
  fi
  if [[ -n "$LOGGER_PID" ]] && kill -0 "$LOGGER_PID" 2>/dev/null; then
    kill "$LOGGER_PID" 2>/dev/null || true
  fi
  wait "$SERVER_PID" 2>/dev/null || true
  wait "$LOGGER_PID" 2>/dev/null || true
  echo "[demo] Stopped."
}

trap cleanup INT TERM EXIT

cd "$ROOT_DIR"

echo "[demo] Starting logger on $SERIAL_PORT @ $BAUD..."
python3 -u ground_station_logger.py \
  --port "$SERIAL_PORT" \
  --baud "$BAUD" \
  --echo >"$LOGGER_LOG" 2>&1 &
LOGGER_PID=$!

sleep 1
if ! kill -0 "$LOGGER_PID" 2>/dev/null; then
  echo "[demo] Logger failed to start."
  tail -n 50 "$LOGGER_LOG" || true
  exit 1
fi

echo "[demo] Starting dashboard server ($HOST:$PORT, refresh ${REFRESH_INTERVAL}s)..."
python3 -u live_dashboard_server.py \
  --db "$DB_PATH" \
  --dashboard "$DASHBOARD_PATH" \
  --interval "$REFRESH_INTERVAL" \
  --host "$HOST" \
  --port "$PORT" >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

sleep 2
if ! kill -0 "$SERVER_PID" 2>/dev/null; then
  echo "[demo] Dashboard server failed to start."
  tail -n 50 "$SERVER_LOG" || true
  exit 1
fi

DASHBOARD_FILE="$(basename "$DASHBOARD_PATH")"
URL="http://$HOST:$PORT/$DASHBOARD_FILE"

echo "[demo] Live dashboard: $URL"
echo "[demo] Logger log: $LOGGER_LOG"
echo "[demo] Server log: $SERVER_LOG"
echo "[demo] Press Ctrl+C to stop both processes."

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" >/dev/null 2>&1 || true
fi

wait -n "$LOGGER_PID" "$SERVER_PID"
