#!/usr/bin/env bash
# 启动检索前置内部服务（默认 0.0.0.0:9101；机房放行 9100–9200）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONDA_BIN="${CONDA_BIN:-/nfs/users/wuqianqian/anaconda3/envs/ipo-risk/bin}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-9101}"

cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "[retrieval-service] root=$ROOT port=$PORT"
exec "$CONDA_BIN/uvicorn" service.app:app --host "$HOST" --port "$PORT" --workers 1
