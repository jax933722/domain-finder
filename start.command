#!/usr/bin/env bash
# ===========================================================================
#  Domain Finder - one-click START (macOS / Linux)
#  macOS: double-click this file (it opens in Terminal).
#  Linux: run ./start.command  (or double-click if your file manager allows).
# ===========================================================================
set -euo pipefail

# Always run from the folder this script lives in.
cd "$(dirname "$0")"

echo "=========================================================="
echo "   Domain Finder - Starting"
echo "=========================================================="
echo

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] Docker is not installed."
  echo "Install Docker Desktop from https://docs.docker.com/get-docker/ and try again."
  read -r -p "Press Enter to close..." _
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "[ERROR] Docker is installed but not running."
  echo "Start Docker Desktop, wait until it is running, then run this again."
  read -r -p "Press Enter to close..." _
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[ERROR] 'docker compose' is not available. Please update Docker Desktop."
  read -r -p "Press Enter to close..." _
  exit 1
fi

# First run: create .env from the template.
if [ ! -f ".env" ]; then
  echo "First run detected: creating .env from .env.example ..."
  cp ".env.example" ".env"
  echo
  echo "  IMPORTANT: edit .env and set SECRET_KEY, FIRST_ADMIN_EMAIL, FIRST_ADMIN_PASSWORD"
  echo "  before real use (defaults are fine for a quick local test)."
  echo
fi

echo "Building and starting containers..."
echo "(The first run can take a few minutes while images download.)"
echo
docker compose up --build -d

echo
echo "Waiting for the app to become ready..."
for _ in $(seq 1 25); do
  sleep 3
  if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health 2>/dev/null | grep -q "200"; then
    break
  fi
done

echo
echo "=========================================================="
echo "   Domain Finder is running!"
echo "=========================================================="
echo "   App:      http://localhost:8080"
echo "   API docs: http://localhost:8080/docs"
echo
echo "   To stop it later, run  stop.command"
echo "=========================================================="
echo

# Open the browser (macOS: open, Linux: xdg-open).
if command -v open >/dev/null 2>&1; then
  open http://localhost:8080
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open http://localhost:8080 >/dev/null 2>&1 || true
fi

read -r -p "Press Enter to close this window..." _
