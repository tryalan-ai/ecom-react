#!/usr/bin/env bash
# Environment image setup for ecom-react.
#
# Runs once per image build, as `alan` with passwordless sudo, from
# /home/alan/workspace and with no saved environment variables.
# Installs dependencies for both the API and frontend, then seeds the database.

set -euo pipefail

ECOM_REPO="/home/alan/workspace/ecom-react"

echo "== System packages =="
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  build-essential curl

echo "== API: install dependencies (frozen lockfile) =="
cd "$ECOM_REPO/API"
npm install --frozen-lockfile

echo "== Frontend: install dependencies (frozen lockfile) =="
cd "$ECOM_REPO/front-end"
npm install --frozen-lockfile

echo "== Database: seed products =="
cd "$ECOM_REPO/API"
npm run seed

echo "setup complete"
