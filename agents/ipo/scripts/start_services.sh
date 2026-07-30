#!/usr/bin/env bash
# IPO 多智能体后端 — 本地依赖服务启动脚本（无 Docker 环境）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$ROOT/.runtime"
CONDA_ENV="ipo-risk"
CONDA_BIN="/nfs/users/wuqianqian/anaconda3/envs/${CONDA_ENV}/bin"

mkdir -p "$RUNTIME/redis" "$RUNTIME/postgres"

export PATH="$CONDA_BIN:$PATH"

# Redis
if ! "$CONDA_BIN/redis-cli" -p 6379 ping >/dev/null 2>&1; then
  echo "[redis] starting on 127.0.0.1:6379 ..."
  "$CONDA_BIN/redis-server" --daemonize yes --port 6379 --bind 127.0.0.1 --dir "$RUNTIME/redis"
else
  echo "[redis] already running"
fi

# PostgreSQL
if ! pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  if [[ ! -f "$RUNTIME/postgres/PG_VERSION" ]]; then
    echo "[postgres] initializing data directory ..."
    initdb -D "$RUNTIME/postgres" -U postgres --auth-host=trust --auth-local=trust -E UTF8
  fi
  echo "[postgres] starting on 127.0.0.1:5432 ..."
  pg_ctl -D "$RUNTIME/postgres" -l "$RUNTIME/postgres.log" -o "-p 5432 -h 127.0.0.1" start
  sleep 2
  psql -h 127.0.0.1 -p 5432 -U postgres -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='ipo_risk'" | grep -q 1 \
    || psql -h 127.0.0.1 -p 5432 -U postgres -d postgres -c "CREATE DATABASE ipo_risk;"
  psql -h 127.0.0.1 -p 5432 -U postgres -d postgres -c "ALTER USER postgres PASSWORD 'postgres';" >/dev/null 2>&1 || true
else
  echo "[postgres] already running"
fi

echo "[ok] Redis + PostgreSQL ready"
