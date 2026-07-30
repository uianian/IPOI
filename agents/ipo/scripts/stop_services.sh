#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONDA_BIN="/nfs/users/wuqianqian/anaconda3/envs/ipo-risk/bin"
export PATH="$CONDA_BIN:$PATH"

if pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  echo "[postgres] stopping ..."
  pg_ctl -D "$ROOT/.runtime/postgres" stop -m fast || true
fi

if "$CONDA_BIN/redis-cli" -p 6379 ping >/dev/null 2>&1; then
  echo "[redis] stopping ..."
  "$CONDA_BIN/redis-cli" -p 6379 shutdown || true
fi

echo "[ok] services stopped"
