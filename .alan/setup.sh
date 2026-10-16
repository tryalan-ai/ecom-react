#!/usr/bin/env bash
# Environment image setup.
#
# Runs once per image build, as `alan` with passwordless sudo, from
# /home/alan/workspace (this environment has several repositories) and with no
# saved environment variables. Anything that needs a secret belongs in
# start.sh, which runs on the booted machine with the environment's variables.
#
# This environment's first repository is ecom-react, so the committed scripts
# live here; the development target is the `alan` monorepo beside it, reached by
# a workspace-relative path.
set -euo pipefail

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ALAN_REPO="$WORKSPACE/alan"
PG_BINDIR=/usr/lib/postgresql/16/bin
PGDATA="$ALAN_REPO/.alan-dev/postgres"
PGPORT=8432

# System packages (build-essential, curl, lsof, postgresql-16, python3-dev,
# python3-setuptools, redis-server, unzip) are installed by the builder from
# .alan/environment.json's packages.apt layer, before this script runs.

# The base image can carry a git credential helper; every session of this
# environment shares the resulting image, so it must not.
git config --global --unset-all credential.helper 2>/dev/null || true

echo "== alan: install dependencies (pnpm 10.28.2, frozen lockfile) =="
cd "$ALAN_REPO"
pnpm install --frozen-lockfile

echo "== alan: build workspace packages consumed from dist =="
pnpm build:packages

echo "== postgres: initialize data directory =="
mkdir -p "$ALAN_REPO/.alan-dev/logs" "$ALAN_REPO/.alan-dev/redis"
if [ ! -f "$PGDATA/PG_VERSION" ]; then
  mkdir -p "$PGDATA"
  chmod 700 "$PGDATA"
  umask 077
  printf '%s\n' "alan_dev" > "$ALAN_REPO/.alan-dev/postgres-password"
  "$PG_BINDIR/initdb" -D "$PGDATA" \
    --username=alan \
    --pwfile="$ALAN_REPO/.alan-dev/postgres-password" \
    --auth-host=scram-sha-256 \
    --auth-local=trust \
    --encoding=UTF8 \
    --no-instructions
fi

# Create the application database now, so the image is usable on first boot.
# A short-lived server is the only way to run CREATE DATABASE.
"$PG_BINDIR/pg_ctl" -D "$PGDATA" -w -t 30 \
  -l "$ALAN_REPO/.alan-dev/postgres.log" \
  -o "-p $PGPORT -h 127.0.0.1 -c unix_socket_directories=/tmp" start
if ! PGPASSWORD=alan_dev "$PG_BINDIR/psql" -h 127.0.0.1 -p "$PGPORT" -U alan -d postgres \
  -tAc "SELECT 1 FROM pg_database WHERE datname = 'alan'" | grep -q 1; then
  PGPASSWORD=alan_dev "$PG_BINDIR/createdb" -h 127.0.0.1 -p "$PGPORT" -U alan alan
fi
"$PG_BINDIR/pg_ctl" -D "$PGDATA" -w -t 30 stop

echo "setup complete"
