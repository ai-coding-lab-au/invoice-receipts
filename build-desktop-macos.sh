#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "A macOS .app must be built on macOS." >&2
  exit 1
fi

"$ROOT/install-desktop-macos.sh"

(
  cd "$ROOT/frontend"
  npm install
  npm run build
)

cd "$ROOT"
"$ROOT/backend/.venv/bin/python" -m PyInstaller --noconfirm --clean backend/desktop-macos.spec
echo "macOS app built at dist/SuperlightInvoice.app"
