#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_datadir.sh
source "$ROOT/_datadir.sh"
resolve_data_dir "$ROOT"

PYTHON="$ROOT/backend/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="python3"

echo "Invoice & Receipts: http://127.0.0.1:8790"
echo "Data directory: $DATA_DIR"
cd "$ROOT/backend"
exec "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8790
