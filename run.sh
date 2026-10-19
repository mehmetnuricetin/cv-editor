#!/usr/bin/env bash
# Start the local CV editor on macOS.
# Creates a virtual environment on first run, then launches Streamlit.
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR=".venv"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Error: '$PYTHON_BIN' not found. Install Python 3.10+ (e.g. 'brew install python')." >&2
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "==> Creating virtual environment in $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if [ ! -f "$VENV_DIR/.deps-installed" ] || [ requirements.txt -nt "$VENV_DIR/.deps-installed" ]; then
  echo "==> Installing dependencies"
  python -m pip install --quiet --upgrade pip
  python -m pip install --quiet -r requirements.txt
  touch "$VENV_DIR/.deps-installed"
fi

PORT="${PORT:-8501}"

echo "==> Starting CV Editor at http://localhost:$PORT"
echo "    Press Ctrl+C to stop."

# Streamlit runs headless (see .streamlit/config.toml), so open the browser here
# once the server is accepting connections.
(
  for _ in $(seq 1 60); do
    if curl -s -o /dev/null "http://localhost:$PORT"; then
      open "http://localhost:$PORT" 2>/dev/null || true
      break
    fi
    sleep 1
  done
) &

exec streamlit run app.py --server.port "$PORT"
