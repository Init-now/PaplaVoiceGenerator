#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
if [[ -f "$VENV_DIR/bin/activate" ]]; then
  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"
elif ! command -v flask >/dev/null 2>&1; then
  echo "Flask CLI not found. Activate your environment or create $VENV_DIR." >&2
  exit 1
fi

PID_FILE="/tmp/papla_flask.pid"

if [[ -f "$PID_FILE" ]]; then
  if kill -0 "$(cat "$PID_FILE")" >/dev/null 2>&1; then
    echo "Server already running with PID $(cat "$PID_FILE")." >&2
    exit 1
  else
    rm -f "$PID_FILE"
  fi
fi

PORT="${FLASK_PORT:-5001}"

if lsof -ti tcp:"$PORT" >/dev/null 2>&1; then
  echo "Port $PORT already in use. Stop the conflicting process or set FLASK_PORT." >&2
  exit 1
fi

export FLASK_APP=papla_voice_web.py
export FLASK_ENV=development

python -m flask run --host=0.0.0.0 --port="$PORT" &
FLASK_PID=$!
sleep 1
if ! kill -0 "$FLASK_PID" >/dev/null 2>&1; then
  wait "$FLASK_PID"
  exit 1
fi

echo "$FLASK_PID" > "$PID_FILE"
echo "Papla Flask server started on http://127.0.0.1:$PORT (PID $FLASK_PID)."
wait "$FLASK_PID"
rm -f "$PID_FILE"
