# 前端联调 — 统一网关 9100

> 契约：`dataset/interface_protocol_v3.4.md`  
> **前端只配一个 Base**：`http://223.3.95.129:9100`（本机 `http://127.0.0.1:9100`）  
> 后端内部：9100 解析/索引 + 反代分析；9101 检索（内部）；9102 分析（被 9100 反代，前端不直连）  
> 当前：**桩模式**解析；解析完成后自动调本机 9101 建索引

```
前端 ──► :9100
           ├─ parse / index-status / agents/status     （status 反代 9102）
           ├─ analysis/start|stream|result             ──反代──► :9102
           └─ report | report/export                   ──反代──► :9102
```

---

## 0. 前置

服务需已启动（三件套；前端只访问 9100）：

```bash
# 9100 网关（解析 + 反代分析）
cd /nfs/users/wuqianqian/IPOI/pdf_parsing && ./scripts/start_expert_parse_service.sh

# 9101 检索（解析完成后自动调用；前端不直连）
cd /nfs/users/wuqianqian/IPOI/retrieval && ./scripts/start_retrieval_service.sh

# 9102 财务/法务分析（ipo-risk；供 9100 反代）
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk && ./scripts/start_analysis_service.sh
```

探活：

```bash
BASE=http://127.0.0.1:9100   # 前端机器改为 http://223.3.95.129:9100

curl -s "$BASE/api/v1/health"
# 期望 stubMode=true，gateway=true，upstreams.analysis.ok=true
curl -s "$BASE/api/v1/agents/status"
# 期望 readyCount=4
```

---

## 1. 启动专家解析

`POST /api/v1/parse/expert/start`  
`Content-Type: multipart/form-data`

| 字段 | 必填 | 说明 |
|------|------|------|
| `file` | 是 | PDF |
| `ticker` | 是 | 建议 Wind 格式，如 `03378.HK` |
| `clientProjectId` | 是 | 前端项目 ID，如 `proj-a1b2c3d4` |
| `fileName` | 是 | 原始文件名 |
| `isBiotech` | 是 | `"true"` / `"false"` |
| `companyName` | 否 | 公司中文名 |
| `listDate` | 否 | 上市日，如 `2025-12-15` |

```bash
BASE=http://127.0.0.1:9100
PDF=/nfs/users/wuqianqian/IPOI/pdf_parsing/pdf/03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf
PROJ="proj-$(date +%s | xargs printf '%x')"

RESP=$(curl -s -X POST "$BASE/api/v1/parse/expert/start" \
  -F "file=@${PDF}" \
  -F "ticker=03378.HK" \
  -F "clientProjectId=${PROJ}" \
  -F "fileName=翰思艾泰.pdf" \
  -F "isBiotech=true" \
  -F "companyName=翰思艾泰" \
  -F "listDate=2025-12-15")
echo "$RESP" | jq
TASK=$(echo "$RESP" | jq -r .data.taskId)
echo "PROJ=$PROJ TASK=$TASK"
```

期望 **202**：`data.taskId`、`status=parsing`。

---

## 2. 轮询解析进度

`GET /api/v1/parse/expert/tasks/:taskId/progress`（前端约 500ms）

```bash
curl -s "$BASE/api/v1/parse/expert/tasks/${TASK}/progress" | jq
# stage: PARSING → READY（progress=100）
```

循环示例：

```bash
while true; do
  STAGE=$(curl -s "$BASE/api/v1/parse/expert/tasks/${TASK}/progress" | jq -r .data.stage)
  echo "stage=$STAGE"
  [ "$STAGE" = "READY" ] || [ "$STAGE" = "FAILED" ] && break
  sleep 0.5
done
```

---

## 3. 取解析结果

`GET /api/v1/parse/expert/tasks/:taskId/result`

```bash
curl -s "$BASE/api/v1/parse/expert/tasks/${TASK}/result" | jq '.data | {taskId,projectId,mode,status,stats}'
# mode=expert；无 images 字段
```

可选 Markdown 逃生口：

```bash
curl -s "$BASE/api/v1/parse/expert/tasks/${TASK}/result/content.md" | head
```

未完成 → **404** `PARSE_NOT_COMPLETED`。

---

## 4. 轮询向量索引状态（分析门控）

`GET /api/v1/projects/:clientProjectId/index-status?taskId=`  
（解析 READY 后后端已自动开始建索引）

| status | 含义 | 前端 |
|--------|------|------|
| `indexing` | 建索引中 | 约 3s 再轮询；分析按钮提示等待 |
| `ready` | 可分析 | 停止轮询，允许 `analysis/start` |
| `failed` | 失败 | toast 错误 |

```bash
curl -s "$BASE/api/v1/projects/${PROJ}/index-status?taskId=${TASK}" | jq
# 或只按项目：
curl -s "$BASE/api/v1/projects/${PROJ}/index-status" | jq
```

循环示例：

```bash
while true; do
  curl -s "$BASE/api/v1/projects/${PROJ}/index-status?taskId=${TASK}" | jq -c .data
  ST=$(curl -s "$BASE/api/v1/projects/${PROJ}/index-status?taskId=${TASK}" | jq -r .data.status)
  [ "$ST" = "ready" ] || [ "$ST" = "failed" ] && break
  sleep 3
done
```

未找到 → **404** `INDEX_STATUS_NOT_FOUND`。

> 大样本（如翰思 700 页）首次建索引需 **数分钟**（本地 embedding）；其间 `progress` 会在 20→65 缓升，`message` 会提示「正在计算向量嵌入…」。不是卡死。同一 `taskId` 再次 prepare 会缓存秒回。

---

## 5. 启动分析（经 9100 反代到 9102）

索引 `ready` 后，**仍用同一个 BASE=9100** 调 analysis（路径不变）。  
默认模型：`google/gemma-4-31b-it`（非 free）。前端可在 body 传 `llmConfig` 覆盖。

```bash
BASE=http://127.0.0.1:9100
PROJ=proj-19fa6ad4a0b
TASK=task_expert_20260728_000008

# start（llmConfig 可选）
RESP=$(curl -s -X POST "$BASE/api/v1/projects/${PROJ}/analysis/start" \
  -H 'Content-Type: application/json' \
  -d "{
    \"clientProjectId\": \"${PROJ}\",
    \"taskId\": \"${TASK}\",
    \"ticker\": \"03378.HK\",
    \"llmConfig\": {
      \"apiBaseUrl\": \"https://openrouter.ai/api/v1\",
      \"apiKey\": \"sk-or-v1-YOUR_KEY\",
      \"model\": \"google/gemma-4-31b-it\"
    }
  }")
echo "$RESP"
AID=$(python3 -c "import json,sys; print(json.load(sys.stdin)['data']['analysisId'])" <<<"$RESP")
echo "AID=$AID"

# stream
curl -N -s "$BASE/api/v1/projects/${PROJ}/analysis/stream?analysisId=${AID}"

# result
curl -s "$BASE/api/v1/projects/${PROJ}/analysis/result?analysisId=${AID}" -o /tmp/analysis_result.json
# report JSON ≡ result.report
curl -s "$BASE/api/v1/projects/${PROJ}/report?analysisId=${AID}" -o /tmp/report.json
# PDF
curl -s "$BASE/api/v1/projects/${PROJ}/report/export?analysisId=${AID}" -o /tmp/report.pdf
python3 <<'PY'
import json
d=json.load(open("/tmp/analysis_result.json"))["data"]
ag=d.get("agents") or {}
leg, fin = ag.get("legal") or {}, ag.get("financial") or {}
print("status", d.get("status"), "overall", d.get("overallScore"), d.get("riskLevel"), "thoughts", len(d.get("thoughts") or []))
print("scoringMode", leg.get("scoringMode"), fin.get("scoringMode"))
print("legalDetail.skills", [s.get("name") for s in ((leg.get("legalDetail") or {}).get("skills") or [])])
print("financeDetail", bool(fin.get("financeDetail")), "dossierPaths", d.get("dossierPaths"))
print("market", (ag.get("market") or {}).get("status") or (ag.get("market") or {}).get("agentId"), "orchestrator", (ag.get("orchestrator") or {}).get("status"))
assert d.get("status")=="completed"
assert leg.get("scoringMode") and fin.get("scoringMode")
assert fin.get("financeDetail") is not None
assert (leg.get("legalDetail") or {}).get("skills")
mkt = ag.get("market") or {}
assert mkt.get("agentId")=="market"
assert mkt.get("status") in {None, "completed", "failed", "skipped"} or mkt.get("reportMarkdown") or mkt.get("marketDetail")
assert (ag.get("orchestrator") or {}).get("status")=="completed"
print("OK: v3.4 result shell")
PY
```

| 字段 | 说明 |
|------|------|
| `clientProjectId` | 与路径一致 |
| `taskId` | 可选，关联解析任务 |
| `ticker` | 建议；市场 Agent 优先使用（允许 `03378.HK`） |
| `llmConfig` | 可选；`apiBaseUrl` / `apiKey` / `model` 缺省则用后端默认 |
| `isBiotech` | 可选；`true`→`issuerType=biotech`（≡18a 门控）；解析 meta 已有则可省略 |

期望：start **202**；stream 三路 thought **实时交错**（财务 thought 不必等法务 completed）；初评无 `category`；条件开辩才有 `category`；result 含独立三份 `reportMarkdown`、`phase`/`debate`/`report`；随后 `/report` 与 `result.report` 字段一致；`/report/export` 为非空 PDF。索引未 ready → **409** `INDEX_NOT_READY`。  
无 ticker 且 parse meta 也无股票代码时 market=`skipped`。  
若 9102 未启动：网关返回 **502** `ANALYSIS_UPSTREAM_DOWN`；`/agents/status` 可降级为 `readyCount=0`。

---

## 6. CORS / 前端配置

- 前端**只配一个 Base**：`VITE_API_BASE=http://223.3.95.129:9100`（或等价命名）
- **不要**再配 9101 / 9102
- 浏览器 CORS 由 9100 统一处理

---

## 7. 一键冒烟（复制即跑）

```bash
BASE=http://127.0.0.1:9100
PDF=/nfs/users/wuqianqian/IPOI/pdf_parsing/pdf/mixue-1-30.pdf   # 小文件更快；也可换翰思完整 PDF
PROJ="proj-$(date +%s | xargs printf '%x')"

curl -s "$BASE/api/v1/health" | jq .data.stubMode

RESP=$(curl -s -X POST "$BASE/api/v1/parse/expert/start" \
  -F "file=@${PDF}" \
  -F "ticker=02097.HK" \
  -F "clientProjectId=${PROJ}" \
  -F "fileName=mixue.pdf" \
  -F "isBiotech=false" \
  -F "companyName=蜜雪集團" \
  -F "listDate=2025-02-21")
TASK=$(echo "$RESP" | jq -r .data.taskId)
echo "PROJ=$PROJ TASK=$TASK"

until [ "$(curl -s "$BASE/api/v1/parse/expert/tasks/${TASK}/progress" | jq -r .data.stage)" = "READY" ]; do sleep 0.5; done
curl -s "$BASE/api/v1/parse/expert/tasks/${TASK}/result" | jq '.data.stats'

until ST=$(curl -s "$BASE/api/v1/projects/${PROJ}/index-status?taskId=${TASK}" | jq -r .data.status); \
      echo "index=$ST"; [ "$ST" = "ready" ] || [ "$ST" = "failed" ]; do sleep 3; done
```
