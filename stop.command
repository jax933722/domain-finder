#!/usr/bin/env bash
# ===========================================================================
#  Domain Finder - one-click STOP (macOS / Linux)
#  Stops the app. Your data is preserved.
# ===========================================================================
set -euo pipefail
cd "$(dirname "$0")"

echo "=========================================================="
echo "   Domain Finder - Stopping"
echo "=========================================================="
echo

if ! docker compose version >/dev/null 2>&1; then
  echo "[ERROR] Docker is not available. Is Docker Desktop installed and running?"
  read -r -p "Press Enter to close..." _
  exit 1
fi

docker compose down

echo
echo "=========================================================="
echo "   Domain Finder stopped. Your data has been kept."
echo "=========================================================="
echo
echo "   Tip: to ALSO erase all data and start fresh next time, run once:"
echo "        docker compose down -v"
echo
read -r -p "Press Enter to close this window..." _
