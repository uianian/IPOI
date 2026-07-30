#!/usr/bin/env bash
# 启动 IPO 多智能体 FastAPI 服务（生产环境建议关闭 debug/reload）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONDA_BIN="/nfs/users/wuqianqian/anaconda3/envs/ipo-risk/bin"

"$ROOT/scripts/start_services.sh"

cd "$ROOT"
export IPO_SYSTEM_DEBUG=false
exec "$CONDA_BIN/uvicorn" src.main:app --host 0.0.0.0 --port 8080
