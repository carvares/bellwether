#!/bin/sh
# Start Bellwether as an independent background process and return immediately. Linux and macOS (POSIX sh).
# readlink -f follows a link to this script (for example from the Herdr mod folder) back to the repository.
root="$(dirname "$(dirname "$(readlink -f "$0")")")"
cd "$root" || exit 1
[ -x "$root/.venv/bin/python" ] || { echo "bellwether: $root/.venv/bin/python not found, run uv sync in $root" >&2; exit 1; }
# Output of the widget process goes to start.log, so that a failure before the log file opens is visible. The log
# folder of the system: ~/Library/Logs on macOS, the XDG state folder elsewhere (bellwether/platform/).
case "$(uname -s)" in
  Darwin) state="$HOME/Library/Logs" ;;
  *) case "$XDG_STATE_HOME" in /*) state="$XDG_STATE_HOME" ;; *) state="$HOME/.local/state" ;; esac ;;
esac
logdir="$state/bellwether"
# The first start after the rename from herdr-float: write into the old folder. Making the new folder here would
# stop the widget from moving the old one. The widget moves the old folder, with this start.log, to the new name.
[ ! -e "$logdir" ] && [ -d "$state/herdr-float" ] && logdir="$state/herdr-float"
mkdir -p "$logdir"
# start.log only grows: empty it when it is larger than 1 MiB.
[ -f "$logdir/start.log" ] && [ "$(wc -c <"$logdir/start.log")" -gt 1048576 ] && : >"$logdir/start.log"
# A process of its own, which does not end with the caller: setsid where it exists (Linux), else nohup in the
# background (macOS has no setsid).
if command -v setsid >/dev/null 2>&1; then
  setsid -f "$root/.venv/bin/python" -m bellwether </dev/null >>"$logdir/start.log" 2>&1
else
  nohup "$root/.venv/bin/python" -m bellwether </dev/null >>"$logdir/start.log" 2>&1 &
fi
