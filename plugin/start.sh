#!/bin/sh
# Start herdr-float as an independent background process and return immediately.
# readlink -f follows a linked plugin folder back to the repository.
root="$(dirname "$(dirname "$(readlink -f "$0")")")"
cd "$root" || exit 1
setsid -f "$root/.venv/bin/python" -m herdr_float >/dev/null 2>&1
