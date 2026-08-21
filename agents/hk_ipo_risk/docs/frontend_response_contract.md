# 港股 IPO 风险分析：前端返回格式与后端产物说明

本文以当前代码实现为准，供前端联调。前端统一访问网关 `:9100`；分析服务实际运行于 `:9102`，由网关原样反代。

## 1. 先说结论

`hansiaitai_master_improved_no_embellishment_v3_20260821.json` 是 **CLI 全链路聚合结果**，包含：

- `finance`：财务 Agent 最终结构化结果及其 `trace`
- `legal`：法务 Agent 最终结构化结果及其 `trace`
- `market`：市场 Agent 最终结构化结果及其 `trace`
- `master`：总控 Agent 的冲突检测、辩论历史、终裁、风险因素、D1/D5/D20/D60 走势、上市后验证、总控 Markdown 及 `trace`

它可以称为“四 Agent 的 CLI 最终聚合结果（含各自部分过程轨迹）”，但**不能**称为“HTTP 返回给前端的完整过程与最终返回”，原因是它不包含：

- HTTP 统一外壳 `{success, data}`
- SSE 的 `events.jsonl` 事件序列
- 前端可直接渲染的统一 `thoughts[]`
- `agents.legal|financial|market|orchestrator` HTTP bundle
- `debate` HTTP 对象
- `report_data.py` 生成的 `ReportData`

`service/report_data.py` 写的是**前端综合报告（总控报告视图）映射器**：输入 CLI merged 结果，输出 `result.data.report`，同时也是 `GET /report` 的 `data`。它不是四 Agent 的完整结果容器；完整容器是 HTTP 的 `result.json`。

当前样例关闭了粉饰分析：`analysis_options.embellishment_enabled=false`，所以前端报告不应出现 `dimensions[id=embellishment]` 或 `embellishmentAnalysis`。

## 2. 接口总览

| 方法 | 路径 | 成功码 | 前端用途 |
|---|---|---:|---|
| `GET` | `/api/v1/agents/status` | 200 | 四 Agent 就绪状态 |
| `POST` | `/api/v1/projects/:clientProjectId/analysis/start` | 202 | 启动异步分析 |
| `GET` | `/api/v1/projects/:clientProjectId/analysis/stream?analysisId=...` | 200 SSE | 实时过程、专家报告、总控与完成通知 |
| `GET` | `/api/v1/projects/:clientProjectId/analysis/result?analysisId=...` | 200 | 进行中快照或完整最终结果 |
| `GET` | `/api/v1/projects/:clientProjectId/report?analysisId=...` | 200/404 | 前端综合报告；完成前为 404 |
| `GET` | `/api/v1/projects/:clientProjectId/report/export?analysisId=...` | 200/404 | PDF 二进制 |

除 SSE/PDF 外，JSON 统一使用：

```json
{"success": true, "data": {}}
```

```json
{"success": false, "error": {"code": "ERROR_CODE", "message": "可读错误"}}
```

## 3. start

### 请求

```http
POST /api/v1/projects/proj-xxx/analysis/start
Content-Type: application/json
```

```json
{
  "clientProjectId": "proj-xxx",
  "taskId": "task_expert_20260821_001",
  "ticker": "03378.HK",
  "isBiotech": true,
  "enableEmbellishment": false,
  "llmConfig": {
    "apiBaseUrl": "https://api.deepseek.com",
    "apiKey": "sk-...",
    "model": "deepseek-v4-flash"
  }
}
```

`clientProjectId` 必须与路径一致。解析任务必须存在且 `indexStatus=ready`；否则分别返回 `TASK_NOT_FOUND` 或 `409 INDEX_NOT_READY`。`ticker` 优先于解析 meta，允许 `03378.HK`，后端规范化为五位代码。

### 202 响应

```json
{
  "success": true,
  "data": {
    "analysisId": "analysis_20260821_000001",
    "status": "started"
  }
}
```

前端保存 `analysisId`，随后同时连接 stream，并可按需轮询 result。

## 4. stream（SSE）

```http
GET /api/v1/projects/proj-xxx/analysis/stream?analysisId=analysis_20260821_000001
Accept: text/event-stream
```

每帧格式：

```text
event: thought
data: {"thought":{"id":"...","agentId":"financial","type":"thinking","content":"...","timestamp":"...","meta":{"kind":"model_think"}}}
```

事件及处理建议：

| event | data 核心字段 | 前端行为 |
|---|---|---|
| `agent_status` | `agentId`, `status` | 更新四 Agent 状态；状态为 `running/completed/skipped` |
| `thought` | `thought` | 追加过程流；以 `thought.id` 去重 |
| `phase_change` | `phase` | 切换 `analysis/debate/report` UI |
| `agent_report` | `agentId`, `reportMarkdown`, `agentResult` | 缓存先完成的专家报告 |
| `debate_message` | `message` | 追加真实辩论消息 |
| `debate_complete` | `rounds` | 标记辩论完成 |
| `report_ready` | `report` | 缓存 ReportData，并立即拉取 `/result` 或 `/report` |
| `analysis_complete` | `overallScore`, `riskLevel` | 关闭 SSE、标记终态 |
| `heartbeat` | `timestamp` | 保活，不展示 |

只有实际开辩时才会出现 `phase=debate`、`debate_message`、`debate_complete` 和 `category`。`debate.rounds=0` 是合法的“无需辩论”，不是失败。

`report_ready` 是关键一致性边界：收到它之前，服务端已写完 `report.json`、完整 `result.json` 和 completed meta，因此可以立即请求报告，不存在正常的短暂 404 窗口。

## 5. result

### 进行中响应

```json
{
  "success": true,
  "data": {
    "analysisId": "analysis_20260821_000001",
    "status": "running",
    "phase": "analysis",
    "overallScore": null,
    "riskLevel": null,
    "thoughts": [],
    "agents": {},
    "debate": {"rounds": 0, "messages": [], "completedAt": null},
    "completedAt": null,
    "error": null
  }
}
```

### 完成响应（结构骨架）

```json
{
  "success": true,
  "data": {
    "analysisId": "analysis_20260821_000001",
    "status": "completed",
    "phase": "report",
    "overallScore": 66,
    "riskLevel": "HIGH",
    "analysisOptions": {"embellishmentEnabled": false},
    "thoughts": [],
    "agents": {
      "legal": {
        "agentId": "legal",
        "riskScore": 60.9,
        "riskLevel": "high",
        "summary": "...",
        "reportMarkdown": "...",
        "logText": "...",
        "logEvents": [],
        "scoringMode": "react+rules_floor",
        "rulesFloor": {},
        "legalDetail": {},
        "agentResult": {}
      },
      "financial": {
        "agentId": "financial",
        "riskScore": 75.0,
        "riskLevel": "high",
        "summary": "...",
        "reportMarkdown": "...",
        "logText": "...",
        "logEvents": [],
        "scoringMode": "react+rules_floor",
        "rulesFloor": {},
        "financeDetail": {},
        "agentResult": {}
      },
      "market": {
        "agentId": "market",
        "riskScore": 62.0,
        "riskLevel": "medium",
        "summary": "...",
        "reportMarkdown": "...",
        "logText": "...",
        "logEvents": [],
        "scoringMode": "historical_rules_floor",
        "marketDetail": {},
        "agentResult": {}
      },
      "orchestrator": {
        "agentId": "orchestrator",
        "status": "completed",
        "overallScore": 66,
        "riskLevel": "HIGH",
        "note": "master_verdict",
        "degraded": false,
        "referenceFundamentalScore": 62.3,
        "logText": "...",
        "logEvents": [],
        "master": {},
        "agentResult": {"synthesisNotes": "...", "judgment": {}, "degraded": false}
      }
    },
    "debate": {"rounds": 2, "messages": [], "completedAt": "2026-08-21T06:06:27Z"},
    "report": {},
    "dossierPaths": {"finance": "...", "legal": "...", "market": "...", "master": "..."},
    "completedAt": "2026-08-21T06:06:27Z"
  }
}
```

注意两个枚举层级：顶层/总控 `riskLevel` 是大写 `HIGH|MEDIUM|LOW`；专家 `riskLevel` 当前为小写。市场无股票代码或失败时，`agents.market` 可能只有 `{agentId,status,reason}`。

## 6. report 与 report/export

`GET /report` 返回：

```json
{
  "success": true,
  "data": {
    "overallScore": 66,
    "riskLevel": "HIGH",
    "riskLabel": "高风险",
    "dimensions": [
      {"id": "legal", "name": "法务合规", "score": 60.9},
      {"id": "financial", "name": "财务穿透", "score": 75.0},
      {"id": "market", "name": "市场情绪", "score": 62.0}
    ],
    "riskFactors": [],
    "comparableIPOs": [],
    "riskTimeline": [],
    "pricePathForecast": [],
    "postListingValidation": {},
    "radarData": [],
    "executiveSummary": "...",
    "debateHighlights": [],
    "agentScores": {"legal": 60.9, "financial": 75.0, "market": 62.0},
    "degraded": false,
    "gateWarning": null,
    "referenceFundamentalScore": 62.3
  }
}
```

严格关系：

```text
GET /report 的 response.data === GET /analysis/result 的 response.data.report
```

启用粉饰时，`dimensions` 增加 `embellishment`，并增加 `embellishmentAnalysis`；关闭时两个位置均省略，前端必须按可选字段处理。`comparableIPOs` 当前固定为空数组。

`GET /report/export` 返回 `application/pdf`，文件名为 `IPO风险报告_{ticker}_{YYYY-MM-DD}.pdf`，不是 JSON。

## 7. 后端 CLI 产物位置

以下路径相对 `agents/hk_ipo_risk/`，除非写明绝对位置。

| 产物 | 默认/模式路径 | 说明 |
|---|---|---|
| CLI 主聚合 JSON | `.runtime/mixue_finance_legal.json`，可用 `run_finance_legal.py --out` 覆盖 | finance/legal/market/master merged 数据；用户给出的翰思文件属于此类 |
| 四份 Markdown | `reports/{五位代码}_finance_report.md`、`_legal_report.md`、`_market_report.md`、`_ipo_risk_warning_report.md` | `generate_analysis_report.py --reports-dir` 生成；仅有 master 时生成总控报告 |
| 专家/总控运行日志 | `logs/*.log`、`logs/*.jsonl` | `--log-dir` 可覆盖；`--no-run-log` 可关闭 |
| 财务 dossier | `.runtime/debate/{doc_id}_finance_*.json` | 路径也写入 finance features/trace |
| 法务 dossier | `.runtime/debate/{doc_id}_legal_*.json` | 路径也写入 legal features/trace |
| 市场 dossier | `.runtime/debate/{doc_id}_market_*.json` | 路径也写入 market features/trace |
| 总控 dossier | `.runtime/debate/{doc_id}_master_*.json` | 含 judgment、debate_history、走势、上市后验证、report_markdown |
| 市场缓存/结果 | `.runtime/market/` | 由市场配置决定文件名；含市场及 post-listing JSON 等 |
| 新闻缓存 | 配置的 news 目录下 `{stock_code}.csv`，Firecrawl 另有 raw cache | 市场 Agent 的外部证据缓存 |
| CLI 报告生成器输入 | `generate_analysis_report.py --result <merged.json>` | 只读 merged JSON，再输出四份 Markdown |

用户当前样例的总控 dossier 已明确记录为：

```text
/nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/.runtime/debate/hansiaitai_market_debate_riskref_20260821_master_20260821_140627.json
```

## 8. 后端 HTTP 产物位置

每次分析目录：

```text
agents/hk_ipo_risk/.runtime/analyses/{analysisId}/
├── meta.json
├── events.jsonl
├── thoughts.json
├── merged.json
├── result.json
├── report.json
├── logs/
│   ├── legal_run.log（无原始 logger 时由事件合成）
│   └── legal_events.jsonl（同上）
├── {五位代码}_finance_report.md
├── {五位代码}_legal_report.md
├── {五位代码}_market_report.md
└── {五位代码}_ipo_risk_warning_report.md
```

HTTP runner 还会把同名四份 Markdown 再写一份到全局 `agents/hk_ipo_risk/reports/`。各 Agent 的原生日志和 dossier 仍分别写入 `logs/` 与 `.runtime/debate/`，路径汇总到 `result.json.dossierPaths`。

各文件与接口映射：

| 文件 | 对应接口/用途 |
|---|---|
| `meta.json` | 任务状态、phase、分数、完成时间、解析 meta |
| `events.jsonl` | `/analysis/stream` 的可回放 SSE 来源 |
| `thoughts.json` | `/analysis/result.data.thoughts` |
| `merged.json` | 四 Agent 内部完整聚合结果，不直接作为前端契约 |
| `result.json` | `/analysis/result` 的 `data` |
| `report.json` | `/report` 的 `data`，也等于 `result.json.report` |
| 四份 Markdown | 专家独立报告与总控风险预警报告；专家三份嵌入 `agents.*.reportMarkdown` |
| PDF | 不固定落盘；`/report/export` 请求时由 `report.json` 同构数据即时渲染并返回 |

## 9. 前端推荐状态机

```text
start 202
  -> 保存 analysisId
  -> 连接 stream
  -> thought/agent_status/agent_report 持续增量展示
  -> report_ready：保存 report，并拉 result 做最终对账
  -> analysis_complete：关闭 SSE，状态置 completed
```

页面刷新或 SSE 断开后，直接用 `analysisId` 请求 `/analysis/result` 恢复：若仍运行，使用其中的 `thoughts`；若已完成，使用 `agents + debate + report` 重建全页。不要把 CLI merged JSON 直接交给前端渲染。
