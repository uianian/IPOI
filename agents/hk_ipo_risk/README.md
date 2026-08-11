# hk_ipo_risk — 港股 IPO 财务 ‖ 法务多 Agent

独立于 `agents/ipo`。本仓库实现 **财务穿透 Agent** 与 **法务合规 Agent**（默认完整 ReAct：多轮选工具 → 规则托底 → LLM `submit_*` 终裁；失败再服务端托底），并提供 **HTTP 分析服务（9102）** 供前端经 **9100 网关** 调用。

| 能力 | 状态 |
|------|------|
| 财务 / 法务 ReAct + `react+rules_floor` | **已启用**（CLI + HTTP） |
| DebateDossier 落盘 + 独立补证据 API | **素材/接口已备** |
| 总控决策 / 多轮辩论编排 | **占位未启用**（`master=null`） |
| 市场情绪 Agent | **占位 / SSE 标 skipped**（接入规范见下） |

契约文档：[`dataset/interface_new.md`](../../dataset/interface_new.md)  
前端联调冒烟：[`pdf_parsing/docs/frontend_api_smoke.md`](../../pdf_parsing/docs/frontend_api_smoke.md)  
市场情绪接入规范（周杰 / 合并用）：[`docs/market_sentiment_agent_spec.md`](docs/market_sentiment_agent_spec.md)

---

## 目录

1. [架构总览](#1-架构总览)
2. [财务 Agent](#2-财务-agent)
3. [法务 Agent](#3-法务-agent)
4. [Tool / Skill 编排流程](#4-tool--skill-编排流程)
5. [中间结果与最终产物](#5-中间结果与最终产物)
6. [运行脚本与完整命令](#6-运行脚本与完整命令)
7. [CLI 参数详解](#7-cli-参数详解)
8. [示例运行（翰思 18A）](#8-示例运行翰思-18a)
9. [总控决策 / 辩论阶段接口](#9-总控决策--辩论阶段接口)
10. [前端相关：端口 / 输入输出 / HTTP](#10-前端相关端口--输入输出--http)
11. [前端联调示例命令](#11-前端联调示例命令)
12. [批量 18A](#12-批量-18a)
13. [测试与目录](#13-测试与目录)
14. [市场情绪 Agent 接入规范](docs/market_sentiment_agent_spec.md)

---

## 1. 架构总览

```
招股书 PDF
  → pdf_parsing（9100）→ full_parse.json
  → retrieval（9101）→ 向量索引 + 财务/法务检索包
  → hk_ipo_risk（9102）
       ├── FinanceAgent (ReAct)
       └── LegalAgent   (ReAct)
  → 合并结果 JSON + DebateDossier + Markdown 报告
  →（未来）Master / 辩论 → 综合风险报告
```

### 分层

| 层级 | 含义 | 财务 | 法务 |
|------|------|------|------|
| **Tool** | 原子能力，JSON schema 可调用 | `retrieve_finance` / `extract_metrics` / `derive_gates` / `calc_cash_runway` / `run_finance_skill` / `search_finance_evidence` / `run_finance_rule_checks` / `submit_finance_report` | `retrieve_legal` / `run_legal_skill` / `search_legal_evidence` / `run_rule_checks` / `submit_legal_report` |
| **Skill** | 可移植业务包（检索+Prompt+阈值） | 4：profitability / cash_flow / solvency / business_context | 5：governance / shareholder_rights / related_party / contracts_and_ip / regulatory_litigation |
| **Agent** | LLM 决定调谁、何时结束 | ReAct（默认）；可降级 pipeline / rules-only | ReAct（默认）；可降级 rules-only |

Skill vs Tool：**Tool** 无状态原子能力；**Skill** 经 `run_*_skill` 暴露，内部编排检索 + 规则/LLM 抽取 + 阈值。`FinanceSkill.meta()` / `LegalSkill.meta()` 可序列化。

### 职责分轨（页面可重合、归因不重合）

| 主题 | 财务 | 法务 |
|------|------|------|
| 对赌/赎回/优先股 | 表内 `CV_PREF` → `CV_PREF_LIABILITY` | 协议条款/清理 → `REDEMPTION_*` |
| 管线/临床 | 只解释钱与商业化，**不计**临床阶段分 | §3.5 / IP Skill |
| 现金消耗/跑道 | §3.4 `CASH_RUNWAY_*` / `BURN_YOY_UP_30` | 不进法务分 |
| 关联交易占比 | 不做独立占比打分 | §3.2 + 關連交易专章表/百分比率抽取 |

### 发行人类型

| `--issuer-type` | 门控 | 财务 `business_context` | 法务 |
|-----------------|------|-------------------------|------|
| `general` | 跳过 2.4 / 3.5；盈利则跳过 3.4 | 加盟/集中度/供应链（按需补证） | 无 3.5 管线 |
| `18a` / `18c` / `biotech` | 启用 2.4、3.5；未盈利算跑道 | 未商业化、OTHER_INCOME≠产品收入；禁加盟错检 | +§3.5 / IP |

---

## 2. 财务 Agent

### 2.1 Tools

| # | Tool | 作用 |
|---|------|------|
| 1 | `retrieve_finance` | 三张财务主表证据 |
| 2 | `extract_metrics` | REV/GP/CFO/NET_LOSS/CV_PREF… |
| 3 | `derive_gates` | 盈利 / 3.4 / biotech 门控；低风险可 `fast_path` |
| 4 | `calc_cash_runway` | 未盈利现金跑道 + burn YoY |
| 5 | `run_finance_skill` | 4 个可移植 Skill（见 `finance_presets` / `finance_schema.yaml`） |
| 6 | `search_finance_evidence` | 补证据（配额 2，缺口可升 3） |
| 7 | `run_finance_rule_checks` | 规则交叉核对；无缺口置 `prefer_llm_submit`，再叫一轮 `submit_finance_report` |
| 8 | `retrieve_context_evidence` | 兼容旧补证路径 |
| 9 | `submit_finance_report` | **唯一结束动作**（+ DebateDossier） |

辩论补证（无 ReAct state）：`search_finance_evidence_standalone(...)`。

### 2.2 Skills（4）

| Skill | 关注点 |
|-------|--------|
| `finance_profitability` | 连续亏损、毛利率、收入质量 |
| `finance_cash_flow` | CFO、烧钱、跑道 |
| `finance_solvency` | 负债、CV_PREF、流动性 |
| `finance_business_context` | 商业模式/融资依赖（18A 侧重未商业化） |

### 2.3 评分 `react+rules_floor`

LLM 负责选工具、四维叙述、初始分；`submit` 时与 `configs/score_rules.yaml` **主题桶 max（规则为锚）** 合并。

| 规则码 | 条件 | delta |
|--------|------|------:|
| `CONTINUOUS_LOSS` / `SINGLE_YEAR_LOSS` | 连续亏损 / 最近完整年亏损 | 25 / 15 |
| `CFO_NEGATIVE` | CFO 持续为负 | 15 |
| `GP_MARGIN_DROP` | 毛利率降幅 >5pp | 10 |
| `CASH_RUNWAY_LT_12` / `CASH_RUNWAY_12_24` | 未盈利跑道 | 20 / 10 |
| `BURN_YOY_UP_30` | 烧钱同比 >30%（全年∨中期） | 15 |
| `CV_PREF_LIABILITY` | CV_PREF 相对资产≥10% 或现金≥50% | 10 |

要点：

- 空参 `submit_finance_report({})` → `submit_recovered`（规则分 + 四维草稿恢复）。
- 硬信号（未盈利/连续亏损/CFO 负）时最终分以合并 breakdown 为准。
- 默认 `reasoning_effort=low`；可用 `--finance-reasoning-effort`。
- 结果看 `features.scoring_mode`、`features.rules_floor`（`llm_score` / `final_score` / `theme_merge`）。

降级开关：`--finance-pipeline`（单次 LLM）、`--finance-rules-only` / `ANALYSIS_FINANCE_RULES_ONLY=1`。

### 2.4 抽数要点

- 主表 text/html 一视同仁；`TBL_BS_COMPANY` 不并入综合 BS。
- 年份区分完整年与中期（`2024_i1`）；盈利门控只用完整年；跑道用最新现金，中期 CFO 按 8 个月年化。
- 18A 无产品收入时保留 `OTHER_INCOME` / `CV_PREF`，勿把其他收入当营收。

---

## 3. 法务 Agent

### 3.1 Tools

| # | Tool | 作用 |
|---|------|------|
| 1 | `retrieve_legal` | 法务检索包 + 全书 grep 基线；observation 含 `hits`（page+excerpt）供 stream 证据卡 |
| 2 | `run_legal_skill(skill_name)` | 定向检索 → LLM 抽取（含 `point_kind`）→ 阈值；返回 `evidence` + 带片段的 `risk_points` |
| 3 | `search_legal_evidence` | 补证据（配额 2，缺口可升 3）；`hits` 列表进 stream |
| 4 | `run_rule_checks` | `extract_legal` + `score_legal`；无缺口且 5 skill 齐全时置 `prefer_llm_submit` |
| 5 | `submit_legal_report` | **唯一结束动作**（LLM 终裁 summary/reasoning → 参考分合并 → DebateDossier） |

辩论补证：`search_legal_evidence_standalone(...)`。

理想路径约 7–8 轮：`retrieve → skill×5 →（可选 search）→ run_rule_checks` → **`prefer_llm_submit` 再叫一轮真正的 `submit_legal_report`**（写 summary/reasoning；`risk_points` 可空由系统从 skill 填充）。LLM 终裁失败 / `max_turns` 耗尽才 `_auto_submit_if_ready` 托底（`auto_submit:rule_checks_ready` 等）。默认 `max_turns=10`。

### 3.2 Skills（5）

| Skill | 文档映射 | 关注点 |
|-------|----------|--------|
| `legal_governance` | 控股/治理 | 控制>50%、一致行动、AB 股 |
| `legal_shareholder_rights` | §3.1 + §3.6 | 对赌赎回 + 上市前权利清理 |
| `legal_related_party` | §3.2 | 关连交易公允/依赖/豁免/**占比** |
| `legal_contracts_and_ip` | +18A 叠 §3.5 | 重大合同 + 核心技术权属 |
| `legal_regulatory_litigation` | 监管/诉讼 | 处罚/许可/仲裁 |

§3.3 集中度仍由规则引擎产出（不占独立 Skill）；§3.4 归财务。

### 3.3 关联交易占比（专章抽取）

离线 RELATED_PARTY 召回常漏「關連交易」专章表格。现行增强：

- `harvest_connected_transactions_from_parse`：从 `full_parse.json` 专章页收割表/文
- `parse_related_party_ratio_signals` / `resolve_related_party_ratio`：区分
  - `share_of_similar_txn`（收入/采购占比）
  - `listing_rule_pct_ratio`（上市规则百分比率，如「最高適用百分比率…低於5%」）
  - `waiver_threshold`（豁免门槛）
- 忽略「預留10%緩衝」等非占比句
- 结果字段：`features["3.2"].ratio_pct` / `ratio_source` / `listing_rule_pct_max` / `waiver_pct_threshold`

翰思验证：`ratio_pct=5.0`，`ratio_source=listing_rule_pct_ratio`，证据页约 418–423。

### 3.4 参考分 `react+rules_floor`

风险点列表与参考分语义分离：列表完整保留；参考分只决定谁进分。

| `point_kind` | 进分 |
|--------------|------|
| `issuer_specific` | 全额（`llm_code_deltas` / `llm_point_deltas`；`confidence=low` 减半） |
| `structural` | × `structural_weight`（默认 0.6） |
| `boilerplate` / `benign_negative` / LLM `disclosure_only` | 不计分 |

合成：分型过滤 → 披露隔离 → 主题 max → **饱和聚合** `100×(1-Π(1-dᵢ/100))` → 托底 `rules_substantive_score`。  
配置：`configs/score_rules.yaml` → `legal.*`。  
报告展示风险分统一 **1 位小数**（底层仍可能为饱和聚合浮点）。

默认 `--legal-reasoning-effort high`（财务默认 `low`）。

---

## 4. Tool / Skill 编排流程

### 4.1 财务 ReAct

```
think
  → retrieve_finance → extract_metrics → derive_gates → (calc_cash_runway)
  → run_finance_skill ×4
  → (search_finance_evidence ≤2/3)
  → run_finance_rule_checks
  → prefer_llm_submit：尽量再叫一轮真正的 submit_finance_report
  → LLM 终裁失败 / 轮次耗尽：服务端 _auto_submit_if_ready 托底
  → 主题 max 规则托底 → DebateDossier 落盘
```

### 4.2 法务 ReAct

```
think
  → retrieve_legal
  → run_legal_skill ×5（含 related_party 专章占比）
  → (search_legal_evidence ≤2/3)
  → run_rule_checks
  → 无缺口且 skill 齐全：prefer_llm_submit → 再叫一轮真正的 submit_legal_report
     有缺口：精选 search 后 submit_legal_report
  → LLM 终裁失败 / 轮次耗尽：服务端 _auto_submit_if_ready 托底
  → point_kind + 饱和聚合 → DebateDossier
```

### 4.3 Think 状态标签

| 标签 | 含义 |
|------|------|
| `ok` | 有 `message.reasoning` |
| `think_from_content` | 无 reasoning，但有 content / tool.reason；**不**触发 missing-think 重试 |
| `reasoning_missing` | 缺 think；整场首次 nudge 重试一次 |
| `reasoning_missing_after_retry` | 重试后仍缺；工具照常执行 |

Token：中间轮 `max_tokens=2048`，收束/submit `4096`。DeepSeek 认 `reasoning_effort`（计入 `max_tokens`）；`reasoning_max_tokens` 仅 OpenRouter 有效。

### 4.4 并行出口

`src/graph/parallel.py`：`asyncio.gather(finance, legal)` →

```json
{
  "doc_id": "...",
  "finance": { "...AgentResult" },
  "legal": { "...AgentResult" },
  "reference_fundamental_score": 66.48,
  "cross_agent_features": [],
  "master": null,
  "note": "...总控辩论未启用"
}
```

`reference_fundamental_score = legal×0.45 + finance×0.55`（参考值，非总控正式输出）。

---

## 5. 中间结果与最终产物

### 5.1 上游输入（本仓消费）

| 输入 | 典型路径 |
|------|----------|
| `full_parse.json` | `pdf_parsing/output/.../full_parse.json` |
| 财务检索包 | `retrieval/.runtime/agent_retrieval_{doc_id}_finance.json` |
| 法务检索包 | `retrieval/.runtime/agent_retrieval_{doc_id}_legal.json` |

HTTP 路径下由 9101 prepare 生成；CLI 可离线 JSON 或 `--use-live-retrieval`。

### 5.2 Agent 运行中

| 产物 | 路径 / 位置 |
|------|-------------|
| 推理日志 | `logs/{doc_name}_{finance\|legal}_{ts}.log` + `.jsonl` |
| ReAct state | 内存：`skill_results` / `metrics` / `queries_used` / `rule_pack` |
| HTTP SSE | `.runtime/analyses/{analysisId}/events`（thought / agent_status） |

### 5.3 交卷后

| 产物 | 路径 |
|------|------|
| 联合结果 JSON | `.runtime/{name}_finance_legal*.json` |
| 财务 dossier | `.runtime/debate/{doc_id}_finance_dossier_{ts}.json` |
| 法务 dossier | `.runtime/debate/{doc_id}_legal_dossier_{ts}.json` |
| Markdown 报告 | `reports/*_report.md`（风险分展示 1 位小数） |
| HTTP result | `.runtime/analyses/{analysisId}/result.json` |

### 5.4 AgentResult 关键字段

- `risk_score` / `risk_level` / `summary` / `score_breakdown` / `risk_points`
- `metrics` / `features`（含 `scoring_mode`、`rules_floor`、`skill_results`、`3.1`–`3.6`）
- `evidence_summary` / `trace`（tool_calls、structured_reasoning）
- `features.debate_dossier_path`

---

## 6. 运行脚本与完整命令

### 6.1 环境

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk
```

推荐联调模型：`--provider deepseek --chat-model deepseek-v4-flash`  
（OpenRouter 可用 `google/gemma-4-31b-it`，避免 `:free` 因 429 不稳定）

### 6.2 上游准备（本地 CLI 调试）

```bash
# 1) 解析（infinity_parser）
conda activate infinity_parser
cd /nfs/users/wuqianqian/IPOI/pdf_parsing
python batch_parse_samples.py \
  --pdf pdf/03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf \
  --output-dir /nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch \
  --gpus auto --page-workers 2 --batch-size 2 \
  --max-new-tokens 16384 --rotate-mode none

# 2) 建索引 + 检索包（ipo-risk）
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/retrieval
python scripts/build_index_from_parse.py \
  --parse /nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/03378_15-12-2025_翰思艾泰－Ｂ_全球發售/full_parse.json \
  --company-name 翰思艾泰 --stock-code 03378 --listing-date 20251215 \
  --doc-id hansiaitai --force

python scripts/simulate_agent_retrieval.py \
  --doc-id hansiaitai --agent finance --issuer-type 18a --top-k 5 \
  --out .runtime/agent_retrieval_hansiaitai_finance.json
python scripts/simulate_agent_retrieval.py \
  --doc-id hansiaitai --agent legal --issuer-type 18a --top-k 5 \
  --out .runtime/agent_retrieval_hansiaitai_legal.json
```

> HTTP 路径：解析完成后 9100 自动调 9101 `/internal/retrieval/prepare`，前端轮询 `index-status=ready` 后再 `analysis/start`。

### 6.3 启动分析 HTTP 服务（9102）

```bash
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk
./scripts/start_analysis_service.sh
# 等价：HOST=0.0.0.0 PORT=9102 uvicorn service.app:app --host $HOST --port $PORT --workers 1
```

环境变量：

| 变量 | 默认 | 含义 |
|------|------|------|
| `PORT` / `ANALYSIS_PORT` | `9102` | 监听端口 |
| `ANALYSIS_FINANCE_RULES_ONLY` | `0` | 强制财务纯规则 |
| `ANALYSIS_LEGAL_RULES_ONLY` | `0` | 强制法务纯规则 |
| `ANALYSIS_DEBATE_DIR` | `.runtime/debate` | dossier 目录 |
| `RETRIEVAL_BASE_URL` | `http://127.0.0.1:9101` | 取 artifacts |
| `PARSE_TASKS_DIR` | `pdf_parsing/.runtime/tasks` | 解析 meta |

### 6.4 生成报告

```bash
python scripts/generate_analysis_report.py \
  --result .runtime/hansiaitai_finance_legal_opt_v4.json \
  --doc-name 翰思艾泰 \
  --pdf-name "03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf" \
  --finance-retrieval /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_finance.json \
  --legal-retrieval /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_legal.json \
  --out reports/hansiaitai_finance_legal_opt_v4_report.md
```

---

## 7. CLI 参数详解

入口：`scripts/run_finance_legal.py`

| 参数 | 说明 |
|------|------|
| `--agent` | `finance` / `legal` / `all`（默认并行） |
| `--doc-id` / `--doc-name` / `--pdf-name` | 文档标识与展示名 |
| `--issuer-type` | `general` / `18a` / `18c` / `biotech` |
| `--parse-json` | `full_parse.json`（财务章节检索 + 法务专章/grep） |
| `--retrieval-finance-json` / `--retrieval-legal-json` | 离线检索包 |
| `--use-live-retrieval` | 忽略离线 JSON，实时混合检索（需已建 index） |
| `--top-k` | 实时检索 top-k |
| `--provider` | `deepseek` / `openrouter` / `openai` / `vllm` |
| `--chat-model` / `--api-key` / `--api-base` | 覆盖默认（可读 `agents/ipo/configs/settings.yaml`） |
| `--reasoning-effort` | 全局默认：`low` / `high` / `max` |
| `--finance-reasoning-effort` | 财务（默认 **low**） |
| `--legal-reasoning-effort` | 法务（默认 **high**） |
| `--max-turns` | ReAct 上限（未传时财务/法务均默认 **10**） |
| `--legal-rules-only` | 法务强制规则链 |
| `--finance-pipeline` | 财务单次 LLM（非 ReAct） |
| `--finance-rules-only` / `--no-finance-llm` | 财务纯规则 |
| `--use-llm` | 仅与 `--legal-rules-only` 联用：规则路径 LLM 增强 |
| `--out` | 结果 JSON |
| `--log-dir` / `--no-run-log` | 推理日志目录 / 关闭 |

---

## 8. 示例运行（翰思 18A）

解析路径若使用 `samples_batch_old`，按实际 `full_parse.json` 替换。

### 8.1 财务 + 法务并行（推荐）

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk

python scripts/run_finance_legal.py \
  --agent all \
  --doc-id hansiaitai \
  --doc-name 翰思艾泰 \
  --pdf-name "03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf" \
  --issuer-type 18a \
  --parse-json "/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch_old/03378_15-12-2025_翰思艾泰－Ｂ_全球發售/full_parse.json" \
  --retrieval-finance-json /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_finance.json \
  --retrieval-legal-json /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_legal.json \
  --provider deepseek \
  --chat-model deepseek-v4-flash \
  --finance-reasoning-effort low \
  --legal-reasoning-effort high \
  --max-turns 10 \
  --out .runtime/hansiaitai_finance_legal_opt_v4.json
```

### 8.2 仅法务（验证关联交易占比）

```bash
python scripts/run_finance_legal.py \
  --agent legal \
  --doc-id hansiaitai \
  --doc-name 翰思艾泰 \
  --pdf-name "03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf" \
  --issuer-type 18a \
  --parse-json "/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch_old/03378_15-12-2025_翰思艾泰－Ｂ_全球發售/full_parse.json" \
  --retrieval-legal-json /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_legal.json \
  --provider deepseek \
  --chat-model deepseek-v4-flash \
  --legal-reasoning-effort high \
  --out .runtime/hansiaitai_legal_related_party_v4.json
```

### 8.3 规则对照 / 旧流水线

```bash
# 法务纯规则
python scripts/run_finance_legal.py --agent legal ... --legal-rules-only \
  --out .runtime/hansiaitai_legal_rules_only.json

# 财务纯规则
python scripts/run_finance_legal.py --agent finance ... --finance-rules-only \
  --out .runtime/hansiaitai_finance_rules.json

# 财务旧单次 LLM
python scripts/run_finance_legal.py --agent finance ... --finance-pipeline \
  --out .runtime/hansiaitai_finance_pipeline.json
```

### 8.4 近期联调快照

| 产物 | 分数 | 说明 |
|------|------|------|
| `reports/hansiaitai_finance_legal_opt_v4_report.md` | 财务 **75.0** / 法务 **60.9** | 关联交易 `ratio_pct=5.0`；报告分一位小数 |
| `reports/hansiaitai_finance_legal_opt_v3_report.md` | 财务 75 / 法务 ~52 | 占比增强前 |
| 蜜雪低风险对照 | 财务 **0 / very_low** | `.runtime/mixue_finance_react_token_slim_v2.json` |

---

## 9. 总控决策 / 辩论阶段接口

### 9.1 现状

| 组件 | 状态 |
|------|------|
| `DebateDossier` / `DebateClaim`（`src/models/debate.py`） | 交卷时落盘 |
| `cross_agent_features` / `master` | 恒为 `[]` / `null` |
| 多轮辩论编排 | **未实现** |
| 独立补证据函数 | **已实现**，待总控调用 |

### 9.2 Dossier 结构（可供总控回看）

```text
DebateDossier
  risk_score / risk_level / summary / reasoning
  claims[]:
    code, level, statement, reasoning
    evidence_refs[]（页码/切片）
    retrieval_queries[]（该主张相关 query）
  retrieval_queries[]（全程检索记录）
  negative_findings / rule_flags / run_log
  client_project_id / task_id / analysis_id
```

路径：`.runtime/debate/{doc_id}_{finance|legal}_dossier_{ts}.json`  
读写：`save_dossier` / `load_dossier`。

### 9.3 补证据 API（辩论阶段可调用）

**法务**（`src/skills/legal_toolbox.py`）：

```python
await search_legal_evidence_standalone(
    doc_id=...,
    parse_json=...,
    query=...,          # 可取自 dossier.retrieval_queries
    intent="business_context",
    section_hint=...,
    top_k=6,
)
```

**财务**（`src/skills/finance_toolbox.py`）：

```python
await search_finance_evidence_standalone(
    doc_id=...,
    parse_json=...,
    query=...,
    intent="business_context",
    section_hint=...,
    top_k=6,
)
```

设计意图：总控判定证据不足时，按 dossier 记录的 query **增量检索**；当前 **不会** 在辩论中自动重跑完整 `run_*_skill` ReAct。

### 9.4 跨 Agent 主题表（未来总控）

模型：`src/models/cross_agent.py`

| 主题 | 财务 | 法务 | 总控（未来） |
|------|------|------|--------------|
| 赎回/优先股 | `CV_PREF_LIABILITY` | `REDEMPTION_*` | 兑付/上市前清理 |
| 加盟 | 收入依赖（general） | 合同责任 | 商业模式风险 |
| 供应链 | 成本/集中 | 供应协议 | 供应链风险 |
| 海外 | 汇率/收入 | 境外监管 | 出海合规 |
| 数据 | 相关收入 | 隐私合规 | 数据业务风险 |

---

## 10. 前端相关：端口 / 输入输出 / HTTP

### 10.1 端口拓扑

```
前端 ──► :9100（解析网关 + 反代分析）
           ├─ parse / index-status     （本机）
           ├─ analysis/*  ──反代──► :9102（本仓）
           └─（内部）9101 检索 prepare / artifacts
```

| 端口 | 服务 | 前端是否直连 |
|------|------|--------------|
| **9100** | 解析 + 网关 | **是**（唯一 Base） |
| **9101** | 检索 | 否 |
| **9102** | 财务/法务分析（本仓） | 否（经 9100 反代） |

前端配置：只设 `VITE_API_BASE=http://<host>:9100`，**不要**配 9101/9102。

### 10.2 本仓暴露的 HTTP 路由（9102）

前缀：`/api/v1/projects/{clientProjectId}/...`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` 或 `/api/v1/health` | 探活 |
| POST | `.../analysis/start` | 启动分析 → **202** `{analysisId, status}` |
| GET | `.../analysis/stream?analysisId=` | SSE：thought / agent_status / analysis_complete / heartbeat |
| GET | `.../analysis/result?analysisId=` | 完整结果或进行中快照 |

实现：`service/app.py`、`service/routes_analysis.py`、`service/analysis_runner.py`、`service/thought_mapper.py`。

法务 Thought 映射（`map_legal_event`）与财务对齐：消费 pipeline 顶层 `evidence_hits`、工具 `output.hits`/`evidence`、以及 `output.risk_points`；ReAct 默认 `translate_think=True`（繁中展示 + `meta.rawThink`）。

### 10.3 start 输入

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

| 字段 | 必填 | 说明 |
|------|------|------|
| `clientProjectId` | 是 | 与路径一致 |
| `taskId` | 建议 | 关联解析任务；用于找 meta / 检索包 |
| `llmConfig` | 否 | 覆盖后端默认模型 |
| `isBiotech` | 否 | 覆盖发行人类型 → `biotech` / `general`；`true` 与 CLI `18a`/`18c` **门控等价** |

前置：解析任务存在且 `indexStatus=ready`，否则 **409** `INDEX_NOT_READY`。

服务端解析 meta 后实际使用：

- `parseJsonPath` → `full_parse.json`
- `retrieval/.runtime/agent_retrieval_{taskId}_{finance|legal}.json`（或 9101 artifacts）
- `issuerType` / `companyName` / `fileName`

### 10.4 stream / result 输出

**SSE 事件**

| 事件 | 数据要点 |
|------|----------|
| `agent_status` | `{agentId, status}`：`running` / `completed` / `skipped` |
| `thought` | `{thought: Thought}`：繁体 `content` + 可选 `meta`（tool/evidence/metrics） |
| `analysis_complete` | `{overallScore, riskLevel}` |
| `heartbeat` | 约 15s |

Agent 展示顺序：先刷完 **legal** thought，再刷 **financial**（内部并行，对外有序）。`market` 本轮 `skipped`；`orchestrator` 用参考分收尾。

**法务 / 财务 Thought 对齐（前端可共用渲染）**

两端共用契约 `meta.kind`（不新增 `legal_*` kind）：

| `meta.kind` | 何时出现（法务） |
|-------------|------------------|
| `model_think` | 每轮 `react_turn`（推理过程；`content` 繁中，`rawThink` 原文） |
| `tool_call` / `tool_result` | 工具开始 / 完成（含规则流水线 `parse_grep` 等） |
| `evidence` | **中段实时**：`evidence_hits` 或 `output.hits`/`evidence`（含 `page` + `excerpt`） |
| `risk_point` | skill / 规则产出风险点（可带 `ref=p.N` 与证据片段） |
| `finance_tables` / `finance_metrics` | 仅财务 |

规则链（`LEGAL_RULES_ONLY` / 无 LLM 回退）与 ReAct 均会在中段推送 `evidence`，不只在终局 `result`。`result.data.thoughts` 与 stream 落盘一致。

**result.data（完成时）**

```json
{
  "analysisId": "...",
  "status": "completed",
  "overallScore": 66,
  "riskLevel": "HIGH",
  "thoughts": [ /* Thought[] */ ],
  "agents": {
    "legal": {
      "agentId": "legal",
      "riskScore": 60.9,
      "riskLevel": "high",
      "summary": "…",
      "reportMarkdown": "…（与 financial 同文）…",
      "logText": "…",
      "logEvents": [],
      "scoringMode": "react+rules_floor",
      "rulesFloor": { "finalScore": 60.9, "rulesScore": 55, "saturatedScore": 60.9 },
      "legalDetail": {
        "skills": [{ "name": "legal_governance", "nRiskPoints": 1, "confidence": "medium", "exists": true }],
        "riskPointCount": 8
      },
      "agentResult": {}
    },
    "financial": {
      "agentId": "financial",
      "riskScore": 75.0,
      "riskLevel": "high",
      "scoringMode": "react+rules_floor",
      "rulesFloor": { "finalScore": 75, "rulesScore": 75, "llmScore": 70 },
      "financeDetail": { "tables": [], "metrics": [], "gates": {}, "cashBurn": null },
      "agentResult": {}
    },
    "market": { "agentId": "market", "status": "skipped", "reason": "not_implemented" },
    "orchestrator": {
      "agentId": "orchestrator",
      "status": "placeholder",
      "overallScore": 66,
      "riskLevel": "HIGH",
      "note": "weighted_reference_score"
    }
  },
  "dossierPaths": { "finance": "...", "legal": "..." },
  "completedAt": "..."
}
```

要点：顶层 `overallScore` 为 **整数**参考融合分（`legal×0.45+finance×0.55`）；顶层 `riskLevel` 为大写三档，`agents.*.riskLevel` 为 Agent 小写枚举；`rulesFloor` 财务/法务字段不对称。  
Thought / EvidenceSnippet 类型见契约 §10.3（`interface_new.md` **v3.3**）。  
**尚未由本仓实现**：`/report`、`/report/export`、`/rag/query`。

---

## 11. 前端联调示例命令

完整冒烟见 [`pdf_parsing/docs/frontend_api_smoke.md`](../../pdf_parsing/docs/frontend_api_smoke.md)。摘要：

### 11.1 启动三件套

```bash
cd /nfs/users/wuqianqian/IPOI/pdf_parsing && ./scripts/start_expert_parse_service.sh   # 9100
cd /nfs/users/wuqianqian/IPOI/retrieval && ./scripts/start_retrieval_service.sh         # 9101
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk && ./scripts/start_analysis_service.sh # 9102
```

### 11.2 探活

```bash
BASE=http://127.0.0.1:9100   # 远端改为 http://223.3.95.129:9100
curl -s "$BASE/api/v1/health" | jq
# 期望 upstreams.analysis.ok=true
curl -s http://127.0.0.1:9102/api/v1/health | jq   # 直连分析服务（调试用）
```

### 11.3 解析 → 等索引 → 分析

```bash
BASE=http://127.0.0.1:9100
PDF=/nfs/users/wuqianqian/IPOI/pdf_parsing/pdf/03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf
PROJ="proj-$(date +%s | xargs printf '%x')"

# 启动专家解析
RESP=$(curl -s -X POST "$BASE/api/v1/parse/expert/start" \
  -F "file=@${PDF}" \
  -F "ticker=03378.HK" \
  -F "clientProjectId=${PROJ}" \
  -F "fileName=翰思艾泰.pdf" \
  -F "isBiotech=true" \
  -F "companyName=翰思艾泰" \
  -F "listDate=2025-12-15")
TASK=$(echo "$RESP" | jq -r .data.taskId)
echo "PROJ=$PROJ TASK=$TASK"

# 等解析 READY
while true; do
  STAGE=$(curl -s "$BASE/api/v1/parse/expert/tasks/${TASK}/progress" | jq -r .data.stage)
  echo "stage=$STAGE"; [ "$STAGE" = "READY" ] || [ "$STAGE" = "FAILED" ] && break
  sleep 1
done

# 等索引 ready（大样本可能数分钟）
while true; do
  ST=$(curl -s "$BASE/api/v1/projects/${PROJ}/index-status" | jq -r .data.status)
  echo "index=$ST"; [ "$ST" = "ready" ] || [ "$ST" = "failed" ] && break
  sleep 5
done

# 启动分析（经 9100 反代到 9102）
RESP=$(curl -s -X POST "$BASE/api/v1/projects/${PROJ}/analysis/start" \
  -H 'Content-Type: application/json' \
  -d "{
    \"clientProjectId\": \"${PROJ}\",
    \"taskId\": \"${TASK}\",
    \"isBiotech\": true,
    \"llmConfig\": {
      \"apiBaseUrl\": \"https://api.deepseek.com\",
      \"apiKey\": \"${DEEPSEEK_API_KEY}\",
      \"model\": \"deepseek-v4-flash\"
    }
  }")
echo "$RESP" | jq
AID=$(echo "$RESP" | jq -r .data.analysisId)

# SSE（可落盘后断言）
curl -N -s "$BASE/api/v1/projects/${PROJ}/analysis/stream?analysisId=${AID}" \
  -o /tmp/analysis_stream.sse

# 结果
curl -s "$BASE/api/v1/projects/${PROJ}/analysis/result?analysisId=${AID}" \
  -o /tmp/analysis_result.json
python3 -c "import json;d=json.load(open('/tmp/analysis_result.json'))['data'];print(d['status'],d.get('overallScore'),d.get('riskLevel'),len(d.get('thoughts')or[]))"

# 断言法务 stream 含推理 / 工具 / 中段 evidence（page+excerpt）
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk
python scripts/assert_legal_stream_parity.py --result /tmp/analysis_result.json
python scripts/assert_legal_stream_parity.py --events /tmp/analysis_stream.sse
# 离线自检（无需起服务）
python scripts/assert_legal_stream_parity.py --self-check
```

常见错误：索引未好 → **409** `INDEX_NOT_READY`；9102 未起 → 网关 **502** `ANALYSIS_UPSTREAM_DOWN`。

法务 Thought 单测：`python -m pytest tests/test_legal_thought_mapper.py -q`。

---

## 12. 批量 18A

前置：`pdf_parsing/output/18a_batch/` 已有各公司 `full_parse.json`（见 `batch_summary.json`）。  
脚本对 `status=ok` 名单依次：建索引 → 财务/法务检索包 → `--agent all`（与 §8.1 同参）→ 报告。  
`doc_id` 取股票代码（如 `01244`），`issuer-type=18a`。

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk

# 推荐：前 3 家（默认 finance=low / legal=high / max-turns=10）
python scripts/batch_finance_legal_18a.py --n 3

# 前 10 家；索引已存在时不强制重建
python scripts/batch_finance_legal_18a.py --n 10 --no-force-index

# 索引与检索包已就绪，只跑联合分析 + 报告
python scripts/batch_finance_legal_18a.py --n 5 --skip-index --skip-retrieval

# 从第 4 家起再跑 5 家；单家失败继续
python scripts/batch_finance_legal_18a.py --n 5 --start 3 --continue-on-error
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `--n` | `3` | `batch_summary.json` 中 `ok` 的前 N 家 |
| `--start` | `0` | 0-based 起始 |
| `--batch-dir` | `pdf_parsing/output/18a_batch` | 解析输出目录 |
| `--retrieval-dir` / `--agent-dir` | IPOI 默认路径 | 工程根目录 |
| `--force-index` / `--no-force-index` | force 开 | 建索引是否 `--force` |
| `--skip-index` / `--skip-retrieval` | 关 | 跳过建索引 / 检索包 |
| `--top-k` | `5` | 检索包 top-k |
| `--provider` / `--chat-model` | `deepseek` / `deepseek-v4-flash` | LLM |
| `--api-key` / `--api-base` | 无 | 覆盖 API |
| `--finance-reasoning-effort` | `low` | 财务思考强度（同 §8.1） |
| `--legal-reasoning-effort` | `high` | 法务思考强度（同 §8.1） |
| `--max-turns` | `10` | ReAct 上限 |
| `--continue-on-error` | 关 | 单家失败继续下一家 |

产物约定：

| 类型 | 路径 |
|------|------|
| 检索包 | `retrieval/.runtime/agent_retrieval_{股票代码}_{finance\|legal}.json` |
| 联合 JSON | `.runtime/18a_{股票代码}_finance_legal.json` |
| 报告 | `reports/18a_{股票代码}_finance_legal_report.md` |
| DebateDossier | `.runtime/debate/{股票代码}_{finance\|legal}_dossier_{ts}.json` |

---

## 13. 测试与目录

### 13.1 单测

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk
python -m pytest tests/test_legal_react.py tests/test_legal_thought_mapper.py \
  tests/test_finance_react_skills.py tests/test_finance_submit_recover.py \
  tests/test_related_party_ratio.py -q
python scripts/assert_legal_stream_parity.py --self-check
```

### 13.2 关键目录

```
agents/hk_ipo_risk/
├── README.md
├── docs/
│   └── market_sentiment_agent_spec.md   # 市场情绪接入规范（合并用）
├── configs/                 # score_rules / finance_schema / legal_schema
├── scripts/
│   ├── run_finance_legal.py
│   ├── batch_finance_legal_18a.py
│   ├── assert_legal_stream_parity.py
│   ├── generate_analysis_report.py
│   └── start_analysis_service.sh
├── service/                 # FastAPI 9102
├── src/
│   ├── agents/              # finance_agent / legal_agent / react_loop
│   ├── skills/              # toolbox / presets / extract_* / score_*
│   ├── models/              # debate / evidence / cross_agent
│   ├── tools/               # schemas / retrieval_tool / llm_client
│   ├── graph/parallel.py
│   └── llm/prompts.py
├── tests/
├── logs/  reports/  .runtime/debate/  .runtime/analyses/
```

### 13.3 实现索引（按主题）

| 主题 | 文件 |
|------|------|
| 财务工具与托底 | `src/skills/finance_toolbox.py` / `finance_presets.py` |
| 法务工具与饱和分 | `src/skills/legal_toolbox.py` / `legal_presets.py` / `legal_point_kind.py` |
| 关联交易占比 | `src/skills/extract_legal.py` |
| 辩论素材 | `src/models/debate.py` |
| HTTP Thought 映射 | `service/thought_mapper.py` |
| 规则配置 | `configs/score_rules.yaml` |
| 市场情绪接入规范 | [`docs/market_sentiment_agent_spec.md`](docs/market_sentiment_agent_spec.md) |
