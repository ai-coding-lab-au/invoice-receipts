#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/frontend"
npm install
npm run build
echo "Interface rebuilt into backend/app/static"
