#!/bin/sh
# Start herdr-float as an independent background process and return immediately.
# readlink -f follows a linked plugin folder back to the repository.
root="$(dirname "$(dirname "$(readlink -f "$0")")")"
cd "$root" || exit 1
[ -x "$root/.venv/bin/python" ] || { echo "herdr-float: $root/.venv/bin/python not found, run uv sync in $root" >&2; exit 1; }
# Output of the widget process goes to start.log, so that a failure before the log file opens is visible.
logdir="$HOME/.local/state/herdr-float"; mkdir -p "$logdir"
setsid -f "$root/.venv/bin/python" -m herdr_float </dev/null >>"$logdir/start.log" 2>&1
