# 市场情绪 Agent 接入规范

> **读者**：周杰（市场情绪 Agent 开发）、`hk_ipo_risk` 集成方  
> **用途**：合并前对齐代码落点、报告、9102 契约、输入输出、Skill/Tool 边界、辩论落盘与补证据；标明现阶段无法确认的闸门  
> **权威契约**：本仓 [`README.md`](../README.md) §1 / §5 / §9 / §10；前端 [`dataset/interface_new.md`](../../../dataset/interface_new.md)  
> **数据交接**：[`market/市场情绪数据使用报告_交接周杰.md`](../../../market/市场情绪数据使用报告_交接周杰.md)  
> **撰写日期**：2026-08-11

---

## 0. 目的与范围

### 0.1 一句话

把市场情绪 Agent 合入 [`agents/hk_ipo_risk`](../)，与财务 / 法务共用 **9102** 分析服务与同一套 ReAct · Tool · Skill · DebateDossier 契约；**主分析输入**为已落地宽表，按股票代码定位公司并做数据分析 + LLM 风险打分。

### 0.2 范围内

| 项 | 说明 |
|----|------|
| 代码落点 | 与财务 / 法务镜像的目录与文件名 |
| 独立 Markdown 报告 | 沿用财务 / 法务报告骨架，单独成文 |
| HTTP / 端口 | 三 Agent 共用 9102；前端只打 9100 |
| 输入输出 | 对齐 `analysis/start` / stream / result |
| Skill / Tool 边界 | 便于后续封装复用 |
| 产物与辩论落盘 | 对齐 `DebateDossier` / `EvidenceRef` |
| 补证据 | ReAct 内 + `*_standalone` |
| 可选检索包 | 若需招股书原文证据，路径命名强制与财务 / 法务一致 |

### 0.3 非目标（本规范不要求周杰单独交付）

- 总控多轮辩论编排（仍由集成方 / 总控占位演进）
- 前端独立端口或新 Base URL
- 另起一套 `retrieval/` 目录、自定义包名（如 `{stock}_sentiment.json`）
- 本规范文档本身不实现 `market_agent.py`（仅定接口）

### 0.4 当前本仓状态

| 组件 | 状态 |
|------|------|
| 财务 / 法务 Agent | 已启用（CLI + HTTP） |
| 市场情绪 Agent | **占位**：SSE `market=skipped`，`result.agents.market.reason=not_implemented` |
| 宽表数据工程 | 已在 `IPOI/market/` 落地 |

---

## 1. 代码落点规范（与财务 / 法务对齐）

周杰若在独立 clone 上开发，**合并时必须按下列路径落盘**，禁止把市场情绪整树挂在仓外自建包名下后只「拷结果」。

### 1.1 目录与文件映射

| 层级 | 财务 / 法务（现有） | 市场情绪（应对齐） |
|------|-------------------|-------------------|
| Agent | `src/agents/finance_agent.py` / `legal_agent.py` | `src/agents/market_agent.py` |
| Toolbox | `src/skills/finance_toolbox.py` / `legal_toolbox.py` | `src/skills/market_toolbox.py` |
| Skill 预设 | `src/skills/finance_presets.py` / `legal_presets.py` | `src/skills/market_presets.py` |
| 可选评分 / 抽数 | `extract_financials.py` / `score_legal.py` 等 | `src/skills/score_market.py`（或等价，放 `skills/`） |
| Tool schema | `src/tools/schemas.py` → `FINANCE_*` / `LEGAL_*` | 同文件增 `MARKET_TOOL_SCHEMAS` |
| Schema YAML | `configs/finance_schema.yaml` / `legal_schema.yaml` | `configs/market_schema.yaml` |
| 打分规则 | `configs/score_rules.yaml` → `finance.*` / `legal.*` | 同文件增 `market.*` |
| CLI | `scripts/run_finance_legal.py --agent finance\|legal\|all` | **扩展** `--agent market`（及 `all` 含 market）；**不推荐**再建第三套顶层 CLI |
| 报告脚本 | `scripts/generate_analysis_report.py` | 扩展支持市场 **或** `scripts/generate_market_report.py` 出**独立** md |
| HTTP | `service/analysis_runner.py`（现跳过 market） | 真实跑 market + SSE / `result.agents.market` |
| Thought 映射 | `service/thought_mapper.py`（已有 `market` id） | 补 market 工具结果 → `meta.kind` 映射 |
| 并行编排 | `src/graph/parallel.py` | 纳入 market（与 finance/legal 并行策略由集成方定） |
| 模型 | `AgentResult.agent: Literal["finance","legal"]` | **必须**扩 `"market"`；`DebateClaim.agent` 同理 |

### 1.2 分层语义（强制）

与财务 / 法务一致，三层不可混用：

| 层 | 含义 | 市场情绪示例 |
|----|------|-------------|
| **Tool** | 无状态原子能力，JSON schema 可调用 | `lookup_market_row` / `retrieve_market` / `run_market_skill` / `search_market_evidence` / `run_market_rule_checks` / `submit_market_report` |
| **Skill** | 可移植业务包（数据 + Prompt + 阈值） | `market_macro` / `market_industry` / `market_ipo_heat`（舆情见 §8） |
| **Agent** | LLM 决定调谁、何时结束 | ReAct；唯一结束动作 **`submit_market_report`** |

Skill vs Tool：Tool 不内嵌业务叙事；Skill 经 `run_market_skill` 暴露，内部编排取数 / 规则或 LLM 抽取 / 阈值。应提供可序列化的 `MarketSkill.meta()`（对齐 `FinanceSkill.meta()` / `LegalSkill.meta()`）。

### 1.3 推荐 ReAct 路径（示意）

```text
lookup_market_row
  → (可选) retrieve_market
  → run_market_skill × N
  → (可选) search_market_evidence
  → run_market_rule_checks   # 无缺口时可置 prefer_llm_submit
  → submit_market_report     # 唯一结束；写 DebateDossier
```

失败 / `max_turns` 耗尽时允许服务端托底（对齐财务 `submit_recovered` / 法务 `_auto_submit_if_ready`），但须在 `features` / `trace` 标明托底原因。

### 1.4 索引 / 检索包路径与命名（需要时强制对齐）

**主链路**：用股票代码等从宽表定位公司并打分，**不依赖**检索包即可完成 MVP。

**仅当**需要招股书页码级证据（发行 / 认购披露核对、辩论补证、报告溯源）时再建索引与 Agent 检索包。禁止自创目录或文件名（如 `market_packs/`、`{stock}_sentiment.json`）。

对齐现有约定（`retrieval/service/prep_runner.py`、本仓 README §5.1）：

| 产物 | 财务 / 法务 | 市场情绪（若启用） |
|------|-------------|-------------------|
| 向量索引（共用） | `retrieval/.runtime/indexes/{doc_id\|taskId}/` | **同一索引目录**；禁止 `indexes_market/` |
| Agent 检索包 | `retrieval/.runtime/agent_retrieval_{id}_finance.json` / `_legal.json` | `retrieval/.runtime/agent_retrieval_{id}_market.json` |
| HTTP prepare 产物键 | `financePackagePath` / `legalPackagePath` | 增 `marketPackagePath`（同命名规则） |
| profile 配置 | `retrieval/configs/agent_retrieval_profiles.yaml` → `finance` / `legal` | **同文件**增 `market:` 段（intent / lexicon 由业务定，文件不可另起） |
| CLI 模拟包 | `simulate_agent_retrieval.py --agent finance\|legal` | `--agent market`（或 `all` 含 market） |
| 9102 消费 | `--retrieval-finance-json` / `--retrieval-legal-json`；HTTP 经 9101 artifacts | `--retrieval-market-json`；HTTP 同 artifacts |
| Agent 侧 Tool | `retrieve_finance` / `retrieve_legal` | 若建包则提供 `retrieve_market`（只读上述路径） |

硬性规则：

1. `{id}` 与财务 / 法务为**同一标识**：HTTP 用解析 `taskId`，CLI 用 `--doc-id`。禁止用股票代码当检索包文件 stem（股票代码只作宽表主键与 meta 字段）。
2. 宏观 / 认购等**结构化字段只读** `market/data/derived/*`；检索包**只服务招股书原文证据**（与 `retrieval/README.md`「与 market 联调」一致）。
3. 若不建包：可不产出 `_market.json`，Tool 列表无 `retrieve_market`；是否纳入 9101 `prepareAgents` 见 §8。

命名示例：

```text
retrieval/.runtime/indexes/hansiaitai/
retrieval/.runtime/agent_retrieval_hansiaitai_finance.json
retrieval/.runtime/agent_retrieval_hansiaitai_legal.json
retrieval/.runtime/agent_retrieval_hansiaitai_market.json   # 若启用
```

---

## 2. 接口与端口规范

### 2.1 端口拓扑（三 Agent 共用，不新增端口）

```text
前端 ──► :9100（解析网关 + 反代分析）
           ├─ parse / index-status
           ├─ analysis/*  ──反代──► :9102（hk_ipo_risk：财务 ‖ 法务 ‖ 市场）
           └─（内部）9101 检索 prepare / artifacts
```

| 端口 | 服务 | 前端是否直连 |
|------|------|--------------|
| **9100** | 解析 + 网关 | **是**（唯一 Base） |
| **9101** | 检索 | 否 |
| **9102** | 分析（本仓，含未来 market） | 否（经 9100 反代） |

前端只设 `VITE_API_BASE=http://<host>:9100`。市场情绪**不得**再开 9103 或独立 FastAPI 给前端。

启动（与现网一致）：

```bash
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk
./scripts/start_analysis_service.sh
# HOST=0.0.0.0 PORT=9102 uvicorn service.app:app --workers 1
```

### 2.2 本仓 HTTP 路由（9102，不变）

前缀：`/api/v1/projects/{clientProjectId}/...`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` 或 `/api/v1/health` | 探活 |
| POST | `.../analysis/start` | 202 `{analysisId, status}` |
| GET | `.../analysis/stream?analysisId=` | SSE |
| GET | `.../analysis/result?analysisId=` | 完整结果或快照 |

实现入口：`service/app.py`、`routes_analysis.py`、`analysis_runner.py`、`thought_mapper.py`。市场逻辑挂入 **同一 runner**，不新开路由前缀。

---

## 3. 输入输出规范

### 3.1 start 输入（与前端对齐，市场不另加字段）

```json
{
  "clientProjectId": "proj-xxx",
  "taskId": "task_expert_...",
  "llmConfig": {
    "apiBaseUrl": "https://api.deepseek.com",
    "apiKey": "sk-...",
    "model": "deepseek-v4-flash"
  },
  "isBiotech": true
}
```

| 字段 | 必填 | 市场侧用法 |
|------|------|------------|
| `clientProjectId` | 是 | 与路径一致；写入 dossier |
| `taskId` | 建议 | 解析 meta / 检索包 id |
| `llmConfig` | 否 | 与财务 / 法务共用覆盖 |
| `isBiotech` | 否 | 发行人类型提示；市场宽表打分通常不门控 18A，但应透传 `issuer_type` 便于日志一致 |

**定位对象公司**（start body **无**股票代码字段）：

1. runner 从解析任务 meta 读取 `stockCode` / `companyName` / `listingDate` / `fileName` / `issuerType` 等  
2. 用规范化后的 `stock_code`（5 位，如 `02097`）查宽表行  
3. `doc_id` / `taskId` 用于检索包与 dossier 命名（与财务 / 法务同一套）

前置：当前共用 start 仍要求解析任务存在且 `indexStatus=ready`（财务 / 法务依赖检索）。市场即便不建自己的包，在共用 start 下仍会等待索引就绪——见 §8。

### 3.2 市场分析输入清单

| 输入 | 典型路径 | 说明 |
|------|----------|------|
| 股票代码 / 公司名 / 上市日 | 解析 meta | 定位宽表 |
| 情绪特征宽表 | `market/data/derived/ipo_sentiment_features.csv` | **主**输入；每家一行 |
| 可选事件表 | `market/data/derived/ipo_events.csv` | 验证 / 报告；**禁止**把 `outcome_*` 当预测特征 |
| 可选检索包 | `retrieval/.runtime/agent_retrieval_{taskId}_market.json` | 仅招股书证据；命名见 §1.4 |
| `full_parse.json` | 解析产物 | 仅当启用招股书补证 / 直播检索时需要 |
| `llmConfig` | start | 共用 |

宽表约定（摘自交接材料，Agent 必须遵守）：

- `NaN` = 缺失，**禁止填 0** 再打分  
- 禁止把 `outcome_*`（上市后收益等）当作预测特征喂给 LLM  
- 舆情历史不足时 MVP 可降权或砍掉（§8）

### 3.3 AgentResult 输出（与财务 / 法务同构）

`src/models/evidence.py` 的 `AgentResult` 扩 `agent: "market"` 后，市场必须填齐：

| 字段 | 要求 |
|------|------|
| `risk_score` | 0–100，越高风险越高；展示 **1 位小数** |
| `risk_level` | 小写枚举（与财务 / 法务一致，如 `very_low`/`low`/`medium`/`high`/`very_high`） |
| `summary` | 一句话摘要 |
| `score_breakdown` | 可解释扣分项列表 |
| `risk_points` | 结构化风险点 |
| `metrics` | 关键宽表指标快照（子分、窗口收益等） |
| `features` | 含 `scoring_mode`、`rules_floor`、`skill_results`、`debate_dossier_path` 等 |
| `evidence_summary` / `trace` | 证据摘要；`tool_calls` / `structured_reasoning` |
| `gates` | 可空；若有数据完整度门控可放此处 |

### 3.4 HTTP result / SSE

**SSE**（`agentId: "market"`）：

| 事件 | 要求 |
|------|------|
| `agent_status` | `running` → `completed`（或失败策略与财务对齐） |
| `thought` | 繁体 `content` + `meta`；复用现有 `meta.kind`，**不新增** `market_*` kind |
| `analysis_complete` | 仍由 runner 统一发（含融合分，权重见 §8） |

`meta.kind` 对齐财务 / 法务：`model_think` / `tool_call` / `tool_result` / `evidence` / `risk_point`；宽表证据无页码时 `evidence` 仍推 `excerpt` + 字段信息。

**`result.agents.market`**（完成时，从占位升级）应具备与 `legal` / `financial` 同级字段：

```json
{
  "agentId": "market",
  "riskScore": 62.0,
  "riskLevel": "medium",
  "summary": "…",
  "reportMarkdown": "…（独立市场报告全文，见 §4）…",
  "logText": "…",
  "logEvents": [],
  "scoringMode": "react+rules_floor",
  "rulesFloor": {},
  "marketDetail": {
    "skills": [],
    "riskPointCount": 0,
    "stockCode": "02097",
    "featureRowKeys": []
  },
  "agentResult": {}
}
```

`dossierPaths` 增 `market`：

```json
"dossierPaths": {
  "finance": ".runtime/debate/..._finance_dossier_....json",
  "legal": ".runtime/debate/..._legal_dossier_....json",
  "market": ".runtime/debate/..._market_dossier_....json"
}
```

日志：`logs/{doc_name}_market_{ts}.log` + `.jsonl`（与 `_*_finance_*` / `_*_legal_*` 并列）。

说明：财务 / 法务当前 `reportMarkdown` 多为**同文联合报告**；市场为**独立报告全文**填入 `agents.market.reportMarkdown`，二者语义不同，前端若共用渲染组件需按 agent 分支（§8）。

---

## 4. 报告规范（独立报告，骨架对齐财务 / 法务）

市场情绪产出**独立** Markdown，**不要**把市场章节塞进现有 `*_finance_legal_report.md` 混排正文。骨架对齐 `reports/hansiaitai_finance_legal_opt_v4_report.md` 的章节节奏。

### 4.1 文件命名

```text
reports/{doc_id}_market_report.md
# 或批量：reports/{stock_code}_market_report.md
```

### 4.2 推荐正文结构

```text
# {公司} — 市场情绪 Agent 结果分析报告

- 生成时间：…
- 股票代码：`02097`
- doc_id / taskId：…
- 评分模式：`react+rules_floor`（或实际值）
- 推理日志：`logs/..._market_....log`
- 宽表：`market/data/derived/ipo_sentiment_features.csv`（行定位说明）
- （可选）检索包：`retrieval/.runtime/agent_retrieval_{id}_market.json`

## 1. 总览

| Agent | 风险分 (0-100↑风险) | 等级 | 摘要 |
|-------|---------------------|------|------|
| 市场情绪 | **xx.x** | … | … |

## 2. 得分与分解

| 代码 | 加分 | 规则 | 指标值 | 说明 | 证据（字段/窗口 或 页） |
|------|------|------|--------|------|------------------------|

## 3. 风险点

| 代码 | 等级 | 说明 | 指标 | 证据 |
|------|------|------|------|------|

## 4. 分维分析

### 宏观 / 行业 / IPO 市场热度 [/ 舆情]

（每维：status、叙述、子分）

## 5. 推理链

- structured_reasoning
- 逐轮工具表（轮次 / 工具 / 状态）

## 6. 关键指标快照

（metrics 表或 JSON）

## 7. DebateDossier

路径：`.runtime/debate/{doc_id}_market_dossier_{ts}.json`
```

### 4.3 展示约定

- 风险分：**1 位小数**（与财务 / 法务一致）  
- 宽表证据列写「字段名 + 窗口 + 取值」；招股书证据写页码  
- 缺失字段在报告中明示「数据缺失，已降权」，禁止写成 0

---

## 5. Skill 编排与 Tool 边界

### 5.1 Tool 清单（合并验收）

| # | Tool | 作用 | 备注 |
|---|------|------|------|
| 1 | `lookup_market_row` | 按 `stock_code` 读宽表行 | 失败明确报错；禁止静默填 0 |
| 2 | `retrieve_market` | 读 market 检索包 / 直播检索 | **仅当启用检索包**；对齐 `retrieve_finance` / `retrieve_legal` |
| 3 | `run_market_skill` | 跑指定 Skill | `skill_name` 枚举见下 |
| 4 | `run_market_rule_checks` | 规则交叉核对 | 可置 `prefer_llm_submit` |
| 5 | `search_market_evidence` | ReAct 内补证 | 配额默认 **2**（缺口可升 3，对齐财务 / 法务） |
| 6 | `submit_market_report` | **唯一结束动作** | 写 `AgentResult` + DebateDossier |

辩论阶段（无 ReAct state）：

```python
await search_market_evidence_standalone(
    doc_id=...,
    stock_code=...,          # 宽表定位
    query=...,               # 可取自 dossier.retrieval_queries
    intent="macro",          # 或 industry / ipo_heat / prospectus_disclosure
    section_hint=...,        # 招股书补证时用
    top_k=6,
    # 可选：parse_json / retrieval 句柄，与 finance/legal standalone 风格一致
)
```

### 5.2 Skill 边界（建议封装，便于复用）

| Skill | 关注点 | 主输入列组（宽表） | 禁止 |
|-------|--------|-------------------|------|
| `market_macro` | 恒指 / 成交 / 南向 / 波动 / 外部宏观 | `hsi_ret_*`、`mkt_turnover_*`、`southbound_net_*`、`hsi_vol_20d`、`vhsi_*`、`dff_*`、`dxy_*`、`us10y_*` 等 | `outcome_*` |
| `market_industry` | 行业收益、超额、资金、同业 IPO 热度 | `ind_ret_*`、`ind_excess_*`、`ind_net_inflow_*`、`ind_ipo_count_*`、`hsics_*` 等 | 把 NaN 当 0 |
| `market_ipo_heat` | 全市场 IPO 热度、认购倍数、破发率窗口 | `ipo_count_*`、`break_rate_*`、`subscription_multiple`、`public_offer_multiple`、`international_placing_multiple` 等 | 用上市后收益反推「预测分」 |
| `market_sentiment_news`（可选） | 舆情 | `news_*` 指针 | MVP 默认不启用或固定中性（§8） |

每个 Skill 输出建议包含：`risk_points` / `evidence`（宽表字段级）/ `confidence` / 子分或 delta 建议；由 `run_market_rule_checks` + `submit_market_report` 做主题合并与托底。

### 5.3 职责边界（相对财务 / 法务）

| 主题 | 财务 | 法务 | 市场情绪 |
|------|------|------|----------|
| 现金流 / 跑道 | ✔ | ✖ | ✖ |
| 对赌条款文本 | 表内负债 | ✔ 协议 | 仅当检索包核对发行相关披露（可选） |
| 恒指 / 行业热度 / 认购倍数 | ✖ | ✖ | ✔（宽表） |
| 招股书页码证据 | 检索包 | 检索包 | 仅可选 market 检索包 |

---

## 6. 产物与辩论证据落盘

### 6.1 路径一览

| 产物 | 路径 |
|------|------|
| DebateDossier | `agents/hk_ipo_risk/.runtime/debate/{doc_id}_market_dossier_{YYYYMMDD_HHMMSS}.json` |
| 联合 / 单跑 JSON | `.runtime/...` 结果中增加 `market` 键（与 `finance` / `legal` 并列） |
| HTTP 分析目录 | `.runtime/analyses/{analysisId}/`（`result.json`、`events.jsonl`、`logs/`…）；`dossierPaths.market` |
| 独立 Markdown | `reports/*_market_report.md` |
| 推理日志 | `logs/{doc_name}_market_{ts}.log` + `.jsonl` |
| （可选）检索包 | `retrieval/.runtime/agent_retrieval_{doc_id\|taskId}_market.json` |

读写：复用 `src/models/debate.py` 的 `save_dossier` / `load_dossier`（`dossier.agent = "market"`）。目录默认 `ANALYSIS_DEBATE_DIR` → `.runtime/debate`。

### 6.2 DebateDossier 结构（与财务 / 法务同一模型）

```text
DebateDossier
  agent = "market"
  doc_id / doc_name / issuer_type
  client_project_id / task_id / analysis_id
  risk_score / risk_level / summary / reasoning
  claims[]:
    code, level, statement, reasoning
    evidence_refs[]
    retrieval_queries[]     # 辩论可重放
  retrieval_queries[]       # 全程记录
  negative_findings / rule_flags / run_log
```

### 6.3 EvidenceRef 适配

模型见 `src/models/evidence.py`（当前 `source_type`: `table` | `text` | `title` | `unknown`）。

| 证据类型 | `page` | `field_code` | `excerpt` | `source_type` |
|----------|--------|--------------|-----------|---------------|
| 招股书（检索包 / 补证） | 有值 | 可选字段码 | 原文 50–200 字 | `text` / `table` / … |
| 宽表 / 行情 | `null` | **列名** | `字段=值；窗口/来源` | 暂用 `table`；是否扩展见 §8 |

`DebateClaim.retrieval_queries` 须可重放，例如：

```json
{
  "kind": "wide_table",
  "stock_code": "02097",
  "fields": ["hsi_ret_20d", "break_rate_60d"],
  "intent": "macro"
}
```

或招股书侧：

```json
{
  "kind": "prospectus",
  "intent": "subscription_disclosure",
  "query": "公开发售 认购倍数",
  "section_hint": null
}
```

---

## 7. 补证据工具

| 场景 | API | 行为 |
|------|-----|------|
| ReAct 内 | `search_market_evidence` | 缺字段再取、同业 / 窗口重算；若已建包则可增量检索招股书；observation 含 `hits`/`evidence` 供 SSE |
| 辩论外 | `search_market_evidence_standalone(...)` | 无 ReAct state；按 dossier 中 query 增量补证 |
| 有检索包 | 走与财务 / 法务相同的离线包或 9101 路径 | **不得**另造包目录 |
| 无检索包 | 仅宽表 / 衍生表 | **不得**伪造页码证据 |
| 禁止 | 辩论中自动重跑完整 ReAct / 全部 Skill | 与 README §9.3 设计意图一致 |

返回结构尽量对齐 `search_finance_evidence_standalone` / `search_legal_evidence_standalone`（`ok`、`hits`、`evidence`、错误信息），便于总控统一调用。

---

## 8. 待确认 / 合并前闸门

以下条目**现阶段无法与本仓实现对齐或拍板**，合并代码前必须逐项确认。未确认前，集成方按「占位 / 可空实现」处理，避免 silent break。

| # | 事项 | 现状 | 合并前动作 |
|---|------|------|------------|
| 1 | 周杰实现是否已按 Tool / Skill / ReAct 分层 | 未知（独立 clone） | diff 对照 §1 路径；不合则先改落盘再合 |
| 2 | 远程 git 落后本仓财务 / 法务更新 | 很可能 | rebase / cherry-pick：`AgentResult`、Thought `meta.kind`、dossier、9102 runner |
| 3 | 是否实际启用 market 检索包 | 未定 | 启用则必须 `_market.json` + `profiles.market` + `retrieve_market`；否则这些可空 |
| 4 | 是否纳入 9101 `prepareAgents: [finance, legal, market]` | 现仅 finance/legal | 纳入则 `indexStatus=ready` 含 market 包；不纳入则市场不因缺 `_market.json` 单独阻塞（仍可能因财务 / 法务等索引） |
| 5 | 共用 start 强制 `INDEX_NOT_READY` | 财务 / 法务需要 | 市场单方无法取消；记录为集成约束 |
| 6 | `EvidenceRef.source_type` 是否扩展（如 `market_series`） | Literal 仅四值 | 扩展需改模型 + 前后端；短期用 `table`+`field_code` |
| 7 | 三方融合分权重 | 现 `legal×0.45+finance×0.55`；总控 placeholder | 市场启用后 overallScore 公式未定 |
| 8 | SSE 对外刷序 | 现 legal → financial；market skipped | 建议 market 接在 financial 之后；需前端确认 |
| 9 | 舆情子分权重 | 交接材料建议 MVP 砍掉或固定中性 50 | 产品确认后写入 `score_rules.yaml` / Skill 开关 |
| 10 | `marketDetail` 字段细目 | 本规范仅给示意 | 与前端约定后再锁 schema |
| 11 | CLI：扩展 `run_finance_legal.py` vs 独立 `run_market.py` | 规范默认扩展现有入口 | 可微调，但产物路径不可改 |
| 12 | `score_rules.yaml` 市场阈值 / 风险码表 | 未合入本仓 | 以周杰背景材料为准，合入时再锁数值 |
| 13 | `agent_retrieval_profiles.yaml` 的 `market` intent 集 | 不存在 | 由周杰定业务字段，但必须落在该文件 `market:` 段 |
| 14 | `agents.market.reportMarkdown` vs 联合报告 | 财务 / 法务同文；市场独立 | 前端展示分支需确认 |

---

## 9. 合并检查清单（集成方）

- [ ] `src/agents/market_agent.py` + `market_toolbox.py` + `market_presets.py` + `MARKET_TOOL_SCHEMAS`  
- [ ] `AgentResult.agent` / dossier `agent` 含 `"market"`  
- [ ] `submit_market_report` 为唯一结束动作，并落盘 `{doc_id}_market_dossier_{ts}.json`  
- [ ] 宽表按 `stock_code` 定位；NaN 不填 0；不用 `outcome_*` 预测  
- [ ] 若有检索包：路径恰为 `retrieval/.runtime/agent_retrieval_{同一id}_market.json`  
- [ ] 独立 `*_market_report.md`；分一位小数  
- [ ] HTTP：不再 `skipped`；SSE / result / `dossierPaths.market` 齐  
- [ ] `search_market_evidence_standalone` 可供总控调用  
- [ ] §8 闸门已开会确认并记录结论  

---

## 10. 参考路径速查

| 主题 | 路径 |
|------|------|
| 本仓 README 契约 | `agents/hk_ipo_risk/README.md` |
| Debate / Evidence 模型 | `src/models/debate.py`、`src/models/evidence.py` |
| 财务 / 法务 toolbox（对照） | `src/skills/finance_toolbox.py`、`legal_toolbox.py` |
| 分析 runner（现跳过 market） | `service/analysis_runner.py` |
| 检索包命名 | `retrieval/service/prep_runner.py` → `agent_retrieval_{task_id}_{agent}.json` |
| 检索 API 设计 | `retrieval/docs/retrieval_api_design.md` |
| 情绪宽表与 Prompt 建议 | `market/市场情绪数据使用报告_交接周杰.md` |
| 多智能体职责 | `.cursor/skills/ipo-multi-agent-orchestration/SKILL.md` |
