#!/usr/bin/env bash
# 启动专家模式 PDF 解析服务；BACKEND_PARSE_ENABLED=1 开启缓存未命中后的实时解析
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONDA_BIN="${CONDA_BIN:-/nfs/users/wuqianqian/anaconda3/envs/infinity_parser/bin}"
HOST="${HOST:-0.0.0.0}"
# 机房防火墙仅放行 9100–9200，默认落在该区间
PORT="${PORT:-9100}"

cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "[expert-parse] root=$ROOT port=$PORT backend_parse_enabled=${BACKEND_PARSE_ENABLED:-0}"
exec "$CONDA_BIN/uvicorn" service.app:app --host "$HOST" --port "$PORT" --workers 1
