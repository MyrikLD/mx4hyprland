#!/bin/sh
set -euo pipefail

PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
WORK="$(cd $(dirname $0) && pwd)"
VENV="${VENV:-$WORK/.venv}"

case "${1:-}" in
    -h|--help)
        echo "Usage: $(basename "$0") [args]"
        echo "Runs watch.py from local venv or via uv if available."
        exit 0
        ;;
esac

cd "$WORK"

if [ -f "$VENV/bin/python" ]; then
    exec "$VENV/bin/python" watch.py "$@"
else
    if command -v uv >/dev/null 2>&1; then
        exec uv run watch.py "$@"
    fi
    if command -v uv >/dev/null 2>&1; then
        exec uv run watch.py "$@"
    else
        echo "'uv' is not found and virtual environment does not exist!"
        exit 1
    fi
fi

