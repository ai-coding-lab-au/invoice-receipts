#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$ROOT/backend/.venv/bin/python"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "The native desktop launcher must run on macOS." >&2
  exit 1
fi
if [[ ! -x "$PYTHON" ]]; then
  echo "Python environment not found. Run ./install-desktop-macos.sh first." >&2
  exit 1
fi
if ! "$PYTHON" -c "import AppKit, webview" >/dev/null 2>&1; then
  echo "macOS desktop dependencies not found. Run ./install-desktop-macos.sh first." >&2
  exit 1
fi

cd "$ROOT/backend"
exec "$PYTHON" desktop.py
