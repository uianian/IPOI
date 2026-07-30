# 检索前置内部服务 — 接口设计

> 负责人：吴倩倩（retrieval 模块）  
> 端口：**9101**（机房放行区间 9100–9200）  
> 前缀：`/internal/retrieval/*`（**不对前端开放**）  
> 状态：P0；解析完成后由 9100 **自动**调用本服务 prepare；前端轮询 9100 的 `index-status`

对齐流水线：[`agents/hk_ipo_risk/README.md`](../../agents/hk_ipo_risk/README.md) 步骤「章节图 → 向量索引 → 财务/法务检索包」。

---

## 0. 目标与边界

| 做 | 不做 |
|----|------|
| 一键 prepare：建索引（含 section_map）+ finance/legal 检索包 | 不返回 markdown/报告给前端 |
| 给分析服务 / Agent 返回**本地路径** | 不替代专家解析（9100） |
| 幂等：已有产物且未 force → 秒级 READY | 不做 SSE 思考流 / 总控 / 前端 `rag/query` |

```text
前端 parse/expert/start（收齐 ticker/companyName/listDate/isBiotech/clientProjectId）
  → 解析服务 meta + 返回 taskId
  → 解析 READY 后 **自动** POST 本服务 /internal/retrieval/prepare
前端轮询 GET /api/v1/projects/{clientProjectId}/index-status（挂在 9100）
  → status=ready 后才允许 analysis/start
分析服务 analysis/start（只传 taskId / clientProjectId）→ Agent
```

> 对齐契约：[`dataset/interface_new.md`](../../dataset/interface_new.md) §6.5 / §7（v3.2）。  
> **建索引触发点**：解析完成后由专家解析服务自动调用本服务，**不是**等 analysis/start。

---

## 1. 参数归属（定稿）

### 1.1 统一 ID：`taskId` ≡ 检索 `docId`

前端契约路径用 **`clientProjectId`**（`proj-…`，每次上传会话唯一）查 index-status；  
检索索引目录仍用解析返回的 **`taskId`**（`task_expert_…`）作为 `doc_id`。  
`clientProjectId` ≠ `taskId`：前者是项目会话，后者是解析/索引键。

### 1.2 解析 `POST /api/v1/parse/expert/start`（前端 → 9100）

| 字段 | 说明 |
|------|------|
| `ticker` | 已有；meta 写 `stockCode = 规范化(ticker)` |
| `clientProjectId` / `fileName` / `isBiotech` | 已有；`clientProjectId` 用于 index-status 路径 |
| `companyName` | Form 可选 |
| `listDate` | Form 可选；规范化为 `listingDate=YYYYMMDD` |
| `issuerType` | 由 `isBiotech` 映射（true→biotech，false→general） |
| `taskId` | 解析服务生成并返回；亦为检索 `doc_id` |

### 1.3 分析 `POST .../analysis/start`

只传 **`taskId`**（+ `clientProjectId`）。其余从解析任务 meta 读取。

### 1.4 仅后端产生

| 字段 | 说明 |
|------|------|
| `parseJsonPath` | 解析完成写入 meta；桩模式指向 `samples_batch/.../full_parse.json` |
| `pdfSha256` | 已有 |

### 1.5 后端固化（不进前端 / 不进 R1 业务字段）

| 参数 | 默认 | 调参位置 |
|------|------|----------|
| `force` | `false` | [`service/config.py`](../service/config.py) `FORCE_REBUILD` / 环境变量 `RETRIEVAL_FORCE` |
| `agents` | `["finance","legal"]` | `PREPARE_AGENTS` |
| `topK` | `5` | `PACKAGE_TOP_K` |

---

## 2. 部署

| 项 | 约定 |
|----|------|
| 代码 | `retrieval/service/` |
| 环境 | `ipo-risk` |
| 启动 | `./scripts/start_retrieval_service.sh`（默认 `0.0.0.0:9101`） |
| 索引根 | `configs/settings.yaml` → `index_root` → `.runtime/indexes` |

---

## 3. Prep 状态机

```text
QUEUED → BUILDING_SECTION → BUILDING_INDEX → BUILDING_PACKAGES → READY
                                                          ↘ FAILED
```

- `BUILDING_SECTION`：随 `build_from_parse` 写入 `meta.json` 内 section_map（无独立长步骤时可快速掠过）
- 幂等：索引存在且包齐全且 `force=false` → 直接 `READY`

---

## 4. 接口清单

### R0 `GET /internal/retrieval/health`

```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "version": "0.1.0",
    "indexRoot": ".../retrieval/.runtime/indexes",
    "forceRebuild": false,
    "prepareAgents": ["finance", "legal"],
    "packageTopK": 5
  }
}
```

### R1 `POST /internal/retrieval/prepare`

分析服务组装（前端不可见）：

```json
{
  "taskId": "dehe",
  "parseJsonPath": "/nfs/.../full_parse.json",
  "companyName": "德合集團",
  "stockCode": "00368",
  "issuerType": "general",
  "listingDate": "20200630"
}
```

响应 **202**：

```json
{
  "success": true,
  "data": {
    "prepId": "prep_20260727_000001",
    "taskId": "dehe",
    "status": "queued",
    "cached": false
  }
}
```

`force` / `agents` / `topK` 读服务配置，不出现在 body。

### R2 `GET /internal/retrieval/preps/{prepId}/progress`

```json
{
  "success": true,
  "data": {
    "prepId": "prep_...",
    "taskId": "dehe",
    "progress": 67,
    "stage": "BUILDING_INDEX",
    "etaSeconds": null,
    "error": null
  }
}
```

终态：`stage=READY` + `progress=100`，或 `FAILED` + `error`。

### R3 `GET /internal/retrieval/docs/{taskId}/status`

```json
{
  "success": true,
  "data": {
    "taskId": "dehe",
    "indexExists": true,
    "financePackageExists": true,
    "legalPackageExists": true,
    "readyForAnalysis": true
  }
}
```

### R4 `GET /internal/retrieval/docs/{taskId}/artifacts`

返回**路径 only**，禁止 chunk 正文：

```json
{
  "success": true,
  "data": {
    "taskId": "dehe",
    "readyForAnalysis": true,
    "indexDir": ".../indexes/dehe",
    "metaPath": ".../indexes/dehe/meta.json",
    "parseJsonPath": ".../full_parse.json",
    "financePackagePath": ".../agent_retrieval_dehe_finance.json",
    "legalPackagePath": ".../agent_retrieval_dehe_legal.json",
    "sectionMapEmbedded": true
  }
}
```

### R5–R10（P1/P2）

| ID | 方法 | 路径 | 阶段 |
|----|------|------|------|
| R5 | POST | `/internal/retrieval/docs/{taskId}/index` | P1 |
| R6 | POST | `/internal/retrieval/docs/{taskId}/packages` | P1 |
| R7 | POST | `/internal/retrieval/docs/{taskId}/section-quality` | P1 |
| R8 | POST | `/internal/retrieval/docs/{taskId}/search` | P1 |
| R9 | GET | `/internal/retrieval/docs` | P2 |
| R10 | DELETE | `/internal/retrieval/docs/{taskId}` | P2 |

---

## 5. 错误码

| code | HTTP | 含义 |
|------|------|------|
| `MISSING_FIELD` | 400 | 缺 taskId / parseJsonPath 等 |
| `PARSE_NOT_FOUND` | 404 | parseJsonPath 不存在 |
| `DOC_NOT_READY` | 404 | 索引或包未就绪 |
| `PREP_NOT_FOUND` | 404 | prepId 不存在 |
| `INDEX_BUILD_FAILED` | 500 | 建索引失败 |
| `PACKAGE_FAILED` | 500 | 检索包失败 |

---

## 6. 德合冒烟样本

| 项 | 值 |
|----|-----|
| parse | `pdf_parsing/output/samples_batch/00368_30-06-2020_德合集團_股份發售-reparse/00368_30-06-2020_德合集團_股份發售/full_parse.json` |
| taskId | `dehe` |
| stockCode | `00368` |
| companyName | `德合集團` |
| listingDate | `20200630` |
| issuerType | `general` |

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/retrieval

python scripts/build_index_from_parse.py \
  --parse ../pdf_parsing/output/samples_batch/00368_30-06-2020_德合集團_股份發售-reparse/00368_30-06-2020_德合集團_股份發售/full_parse.json \
  --company-name 德合集團 --stock-code 00368 --listing-date 20200630 \
  --doc-id dehe --force

python scripts/simulate_agent_retrieval.py --doc-id dehe --agent finance --issuer-type general --top-k 5 \
  --out .runtime/agent_retrieval_dehe_finance.json
python scripts/simulate_agent_retrieval.py --doc-id dehe --agent legal --issuer-type general --top-k 5 \
  --out .runtime/agent_retrieval_dehe_legal.json
```

---

## 7. 落地阶段

| 阶段 | 内容 |
|------|------|
| **P0（当前）** | 本文档 + R0–R4 服务骨架 + 德合 CLI 冒烟 |
| P1 | 解析 meta 写 `parseJsonPath`；扩展 parse Form；R5–R8 |
| P2 | R9–R10；embedding 降级策略 |

封装 CLI：`scripts/build_index_from_parse.py`、`scripts/simulate_agent_retrieval.py`。
