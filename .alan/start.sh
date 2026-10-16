#!/usr/bin/env bash
# Start the services every session of this environment needs.
#
# Runs at every session boot from /home/alan/workspace, and again on a disk
# resume, so it is idempotent: each service is skipped when it is already up.

set -euo pipefail

ECOM_REPO="/home/alan/workspace/ecom-react"
DEV_DIR="$ECOM_REPO/.alan-dev"
mkdir -p "$DEV_DIR/logs"

# Start API server if not already running
if ! curl -s http://localhost:3001/api/health >/dev/null 2>&1; then
  cd "$ECOM_REPO/API"
  nohup npm start > "$DEV_DIR/logs/api.log" 2>&1 &
  echo "Started API server"
else
  echo "API server already running"
fi

# Start frontend dev server if not already running
if ! curl -s http://localhost:5173 >/dev/null 2>&1; then
  cd "$ECOM_REPO/front-end"
  nohup npm run dev > "$DEV_DIR/logs/frontend.log" 2>&1 &
  echo "Started frontend dev server"
else
  echo "Frontend dev server already running"
fi

exit 0
