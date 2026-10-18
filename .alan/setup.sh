#!/usr/bin/env bash
# Environment image setup for ecom-react.
#
# Runs once per image build, as `alan` with passwordless sudo, from
# the repository's own directory with no saved environment variables.
# Installs dependencies for both the API and frontend, then seeds the database.

set -euo pipefail

echo "== API: install dependencies (frozen lockfile) =="
cd API
npm install --frozen-lockfile

echo "== Frontend: install dependencies (frozen lockfile) =="
cd ../front-end
npm install --frozen-lockfile

echo "== Database: seed products =="
cd ../API
npm run seed

echo "setup complete"
