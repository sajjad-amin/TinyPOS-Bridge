#!/bin/bash
# TinyPOS Desktop Client Launcher
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_VENV="$DIR/../.venv/bin/python"

if [ -f "$PARENT_VENV" ]; then
    PYTHON_CMD="$PARENT_VENV"
else
    PYTHON_CMD="python3"
fi

echo "Starting TinyPOS Desktop Client with $PYTHON_CMD..."
exec "$PYTHON_CMD" "$DIR/main.py" "$@"
