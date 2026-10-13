#!/usr/bin/env bash
# Start the services every session of this environment needs.
#
# Runs at every session boot from /home/alan/workspace, and again on a disk
# resume, so it is idempotent: each service is skipped when it is already up.
# The development target is the `alan` monorepo beside this repository.
set -euo pipefail

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ALAN_REPO="$WORKSPACE/alan"
PG_BINDIR=/usr/lib/postgresql/16/bin
PGDATA="$ALAN_REPO/.alan-dev/postgres"
DEV_DIR="$ALAN_REPO/.alan-dev"

mkdir -p "$DEV_DIR/logs" "$DEV_DIR/redis"

if ! "$PG_BINDIR/pg_isready" -h 127.0.0.1 -p 8432 -q; then
  nohup "$PG_BINDIR/postgres" -D "$PGDATA" \
    -h 127.0.0.1 -p 8432 \
    -c unix_socket_directories=/tmp \
    -c wal_level=logical \
    -c max_replication_slots=10 \
    -c max_wal_senders=10 \
    > "$DEV_DIR/postgres.log" 2>&1 &
fi

if ! redis-cli -h 127.0.0.1 -p 8379 ping >/dev/null 2>&1; then
  nohup redis-server --bind 127.0.0.1 --port 8379 --dir "$DEV_DIR/redis" \
    --appendonly yes --maxmemory 256mb --maxmemory-policy noeviction --save "" \
    > "$DEV_DIR/redis.log" 2>&1 &
fi

exit 0
