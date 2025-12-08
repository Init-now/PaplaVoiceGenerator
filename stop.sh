#!/usr/bin/env bash
set -euo pipefail

PID_FILE="/tmp/papla_flask.pid"

if [[ -f "$PID_FILE" ]];
then
  if kill "$(cat "$PID_FILE")" >/dev/null 2>&1; then
    echo "Stopped Papla Flask server (PID $(cat "$PID_FILE"))."
  else
    echo "Failed to stop server via PID file; process may not exist." >&2
  fi
  rm -f "$PID_FILE"
else
  echo "No PID file found at $PID_FILE. Is the server running?" >&2
fi
