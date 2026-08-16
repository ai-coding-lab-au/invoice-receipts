#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
python3 -m venv "$ROOT/backend/.venv"
PYTHON="$ROOT/backend/.venv/bin/python"
if [[ -d "$ROOT/vendor/wheels" ]]; then
  "$PYTHON" -m pip install --no-index --find-links "$ROOT/vendor/wheels" -r "$ROOT/backend/requirements-runtime.txt"
else
  "$PYTHON" -m pip install -r "$ROOT/backend/requirements-runtime.txt"
fi
echo "Installed. Run ./start.sh and open http://127.0.0.1:8790"
