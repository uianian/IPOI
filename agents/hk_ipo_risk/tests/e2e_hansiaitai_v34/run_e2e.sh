#!/usr/bin/env bash
# 重启 9100/9101/9102（STUB_MODE 保持 True），只打 9100 走翰思艾泰全链路。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IPOI="$(cd "$HERE/../../../.." && pwd)"
HK="$IPOI/agents/hk_ipo_risk"
PARSE="$IPOI/pdf_parsing"
RET="$IPOI/retrieval"
LOG="$HERE/logs"
FE="$LOG/frontend"
BE="$LOG/backend"
PY="/nfs/users/wuqianqian/anaconda3/envs/ipo-risk/bin/python"

mkdir -p "$FE" "$BE"
echo "[e2e] IPOI=$IPOI logs=$LOG"

kill_port() {
  local port="$1"
  local pids
  pids="$(ss -lptn "sport = :${port}" 2>/dev/null | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u || true)"
  if [[ -n "${pids}" ]]; then
    echo "[e2e] kill :${port} pids ${pids}"
    kill ${pids} 2>/dev/null || true
    sleep 1
    kill -9 ${pids} 2>/dev/null || true
  fi
}

kill_port 9100
kill_port 9101
kill_port 9102
sleep 1

nohup bash "$PARSE/scripts/start_expert_parse_service.sh" >"$BE/9100.stdout" 2>&1 &
echo $! >"$BE/9100.pid"
nohup bash "$RET/scripts/start_retrieval_service.sh" >"$BE/9101.stdout" 2>&1 &
echo $! >"$BE/9101.pid"
nohup bash "$HK/scripts/start_analysis_service.sh" >"$BE/9102.stdout" 2>&1 &
echo $! >"$BE/9102.pid"

echo "[e2e] waiting health..."
for i in $(seq 1 40); do
  if curl -sf http://127.0.0.1:9100/api/v1/health >/dev/null \
    && curl -sf http://127.0.0.1:9101/health >/dev/null \
    && curl -sf http://127.0.0.1:9102/api/v1/health >/dev/null; then
    echo "[e2e] all healthy"
    break
  fi
  sleep 1
  if [[ "$i" -eq 40 ]]; then
    echo "[e2e] services failed to start" >&2
    tail -n 40 "$BE/9100.stdout" "$BE/9101.stdout" "$BE/9102.stdout" >&2 || true
    exit 1
  fi
done

curl -s http://127.0.0.1:9100/api/v1/health | tee "$FE/health_after_restart.json"
echo
STUB="$($PY -c "import json; print(json.load(open('$FE/health_after_restart.json'))['data'].get('stubMode'))")"
echo "[e2e] stubMode=$STUB"
if [[ "$STUB" != "True" && "$STUB" != "true" ]]; then
  echo "[e2e] refusing to run: STUB_MODE is not true" >&2
  exit 1
fi

cd "$(dirname "$0")"
"$PY" run_pipeline.py
"$PY" assert_v34.py "$LOG"

# 三份 MD 文件名
ls -1 "$HK/reports"/03378_*_report.md | tee "$BE/report_md_files.txt"
test -f "$HK/reports/03378_finance_report.md"
test -f "$HK/reports/03378_legal_report.md"
test -f "$HK/reports/03378_market_report.md"
echo "[e2e] OK"
