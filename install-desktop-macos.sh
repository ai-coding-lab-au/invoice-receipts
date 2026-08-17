#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer must run on macOS." >&2
  exit 1
fi

VENV="$ROOT/backend/.venv"
PYTHON="$VENV/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  python3 -m venv "$VENV"
fi

"$PYTHON" -m pip install -r "$ROOT/backend/requirements-macos.txt"
echo "macOS desktop dependencies installed. Run ./run-desktop-macos.sh"
