# hk_ipo_risk — 港股 IPO 财务 ‖ 法务 ‖ 市场 ‖ 总控多 Agent

独立于 `agents/ipo`。本仓库实现 **财务穿透 Agent**、**法务合规 Agent**（默认完整 ReAct）、**市场情绪 Agent**（上市前首日破发风险 + 上市后 D1/D5–D60）与 **总控决策 Agent**（冲突研判 → 条件辩论 → 粉饰 → 终裁/走势预判 → 上市后验证 → 报告；正式分来自终裁而非对照加权），并提供 **HTTP 分析服务（9102）** 供前端经 **9100 网关** 调用。

当前主链路为四 Agent：财务、法务、市场三路并行探查，随后由总控执行冲突研判、按需辩论、可选粉饰分析和终裁。本文只描述当前代码契约，不再保留历史 PR 合并过程作为运行说明。

| 能力 | 状态 |
|------|------|
| 财务 / 法务 ReAct + `react+rules_floor` | **已启用**（CLI + HTTP） |
| DebateDossier 落盘 + 辩论补证 | **已启用**；财务/法务使用页码直取 + 短关键词，市场使用上市前结构化证据 ID / 字段 / 截止日 |
| 总控决策 / 多轮辩论编排 | **已启用**（LangGraph 总控子图；终裁为正式分；输出 D1/D5/D20/D60 走势预判） |
| 上市后真实行情验证 | **已启用**：自动对齐 D1/D5/D20/D60，计算加权命中分与 D5 重点预警 |
| 市场情绪 Agent | **已启用**：历史校准分 + LLM ReAct + 多空辩论；失败不阻断财务/法务/总控 |

契约文档：[`dataset/interface_protocol_v3.4.md`](../../dataset/interface_protocol_v3.4.md)  
前端联调冒烟：[`pdf_parsing/docs/frontend_api_smoke.md`](../../pdf_parsing/docs/frontend_api_smoke.md)  
市场情绪字段与接入规范：[`docs/market_sentiment_agent_spec.md`](docs/market_sentiment_agent_spec.md)
Git 协作流程（clone / 功能分支 / 网页 PR）：仓库根目录 [`README.md`](../../README.md) 第 7 节。

---

## 目录

1. [架构总览](#1-架构总览)
2. [财务 Agent](#2-财务-agent)（[评分](#23-评分-reactrules_floor) · [抽数](#24-抽数要点) · [检索包契约](#25-检索包契约retrieve_finance-依赖)）
3. [法务 Agent](#3-法务-agent)
4. [Tool / Skill 编排流程](#4-tool--skill-编排流程)
5. [中间结果与最终产物](#5-中间结果与最终产物)
6. [运行脚本与完整命令](#6-运行脚本与完整命令)
7. [CLI 参数详解](#7-cli-参数详解)
8. [示例运行（翰思 18A）](#8-示例运行翰思-18a)
9. [总控决策 Agent](#9-总控决策-agent)
10. [前端相关：端口 / 输入输出 / HTTP](#10-前端相关端口--输入输出--http)
11. [前端联调示例命令](#11-前端联调示例命令)
12. [批量 18A](#12-批量-18a)
13. [测试与目录](#13-测试与目录)
14. [市场情绪 Agent](#14-市场情绪-agent)

---

## 1. 架构总览

```
招股书 PDF
  → pdf_parsing（9100）→ full_parse.json
  → retrieval（9101）→ 向量索引 + 财务/法务检索包（财务为整表 pack，见 §2.5）
  → hk_ipo_risk（9102）
       ├── FinanceAgent (ReAct)：retrieve → extract → skills → 规则托底 → submit 定稿
       ├── LegalAgent   (ReAct)：retrieve → skills → 规则核对 → submit 定稿
       ├── MarketAgent  (正式)：宏观/行业/IPO 市场/舆情 → 首日破发风险 0–100；上市后 D1/D5–D60
       └── MasterAgent  (LangGraph 子图，专家探查之后)：
             冲突研判 →（仅 need_debate）辩论≤3 轮 →（默认启用、可关闭）粉饰 → 终裁/走势预判 → 上市后验证 → 报告
  → 合并结果 JSON + 三专家 DebateDossier + 总控 `*_master_*.json`
    + 四份 MD（`{代码}_finance|legal|market_report.md` + `{代码}_ipo_risk_warning_report.md`）
    + HTTP `result.report` / `/report` JSON + `/report/export` PDF
```

### 分层

| 层级 | 含义 | 财务 | 法务 |
|------|------|------|------|
| **Tool** | 原子能力，JSON schema 可调用 | `retrieve_finance` / `extract_metrics` / `derive_gates` / `calc_cash_runway` / `run_finance_skill` / `search_finance_evidence` / `run_finance_rule_checks` / `submit_finance_report` | `retrieve_legal` / `run_legal_skill` / `search_legal_evidence` / `run_rule_checks` / `submit_legal_report` |
| **Skill** | 可移植业务包（检索+Prompt+阈值） | 4：profitability / cash_flow / solvency / business_context | 5：governance / shareholder_rights / related_party / contracts_and_ip / regulatory_litigation |
| **Agent** | LLM 决定调谁、何时结束 | ReAct（默认）；可降级 pipeline / rules-only | ReAct（默认）；可降级 rules-only |

Skill vs Tool：**Tool** 无状态原子能力；**Skill** 经 `run_*_skill` 暴露，内部编排检索 + 规则/LLM 抽取 + 阈值。`FinanceSkill.meta()` / `LegalSkill.meta()` 可序列化。财务 `retrieve_finance` **只消费**上游整表包，不在 Agent 内切表。

### 职责分轨（页面可重合、归因不重合）

| 主题 | 财务 | 法务 |
|------|------|------|
| 对赌/赎回/优先股 | 表内 `CV_PREF` → `CV_PREF_LIABILITY` | 协议条款/清理 → `REDEMPTION_*` |
| 管线/临床 | 只解释钱与商业化，**不计**临床阶段分 | §3.5 / IP Skill |
| 现金消耗/跑道 | §3.4 `CASH_RUNWAY_*` / `RUNWAY_UNCERTAIN` / `BURN_YOY_UP_30` | 不进法务分 |
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
| 1 | `retrieve_finance` | 消费检索整表包（`TBL_IS` / `TBL_BS` / `TBL_CF` + 可选 `TBL_BS_COMPANY`）；不自行切表 |
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
| `RUNWAY_UNCERTAIN` | 未盈利但跑道算不出（缺 CFO/烧钱序列） | 15 |
| `BURN_YOY_UP_30` | 烧钱同比 >30%（全年∨中期） | 15 |
| `CV_PREF_LIABILITY` | CV_PREF 相对资产≥10% 或现金≥50% | 10 |
| `DATA_INSUFFICIENT_IS` | 18A 抽不出 `NET_LOSS` 且分 <40 | 抬至 **40**（关注档，非 yaml 规则码） |

`submit_finance_report` **定稿顺序**（`finalize_finance_report` / `_validate_submit`）：

1. `_merge_rules_floor`：主题桶 max，规则为锚
2. `_apply_18a_data_insufficient_guard`：18A 缺 `NET_LOSS` 禁止 silent `very_low=0`
3. `_align_narrative_to_level`：改写 summary/reasoning 里残留的旧分数/等级

叙事对齐会处理「規則打分 0.0」「中級（40分）」「定為低（45分）」等与最终 `risk_score` / `risk_level` 不一致的措辞（等级词一并改写，不只改数字）。`high` vs 中文「中等」若语义接近则可能只加注，不强制改写等级词。

要点：

- 空参 `submit_finance_report({})` → `submit_recovered`（规则分 + 四维草稿恢复）。
- 硬信号（未盈利/连续亏损/CFO 负）时最终分以合并 breakdown 为准。
- `max_turns` 耗尽但已有 metrics/gates：`_auto_submit_if_ready` 用 **按 skill 列风险点** 的结构化摘要收束（含 `RUNWAY_UNCERTAIN` 提示），不再用空模板「未觸發規則扣分項」。
- ReAct / pipeline LLM 失败：`score_finance_rules_fallback`；`build_rules_summary` 按已触发规则写摘要，无证据页仍计分。
- 默认 `reasoning_effort=low`；可用 `--finance-reasoning-effort`。
- 结果看 `features.scoring_mode`、`features.rules_floor`（`llm_score` / `final_score` / `theme_merge`）。
- `score_breakdown[].metric_value` 是规则计算使用的机器原值（保留 number 等原始类型）；`metric_display` 是面向报告的“指标 + 期间 + 数值”文本。主题桶合并以规则原值和规则证据页为锚，只从 LLM 同主题项补 `metric_display` / 说明；报告优先展示 `metric_display`，缺失时才回退到 `metric_value`。

降级开关：`--finance-pipeline`（单次 LLM）、`--finance-rules-only` / `ANALYSIS_FINANCE_RULES_ONLY=1`。

### 2.4 抽数要点

实现：`src/skills/extract_financials.py` + `table_utils.py`；别名：`configs/finance_schema.yaml`。

- 主表 **text / html 一视同仁**（解析常把附录主表标成 `text`）；`TBL_BS_COMPANY` 只登记证据，**不并入**综合 BS 指标。
- 年份：完整年 vs 中期（`2024_i1`）；支持表头「二零一八年人民幣千元」、文本表把 `2023年`/`2024年` 拆成多行。盈利门控只用完整年；跑道用最新现金，中期 CFO 按 8 个月年化。
- 18A 无产品收入时保留 `OTHER_INCOME` / `CV_PREF`，勿把其他收入当营收。
- **`NET_LOSS`**：优先「年內/期內溢利(虧損)」底行，税前亏损仅回退；行名括号/繁简/空格归一（含 `動→动`）。IS 未召回时，可用现金流量表「除税前虧損」代理（`extract_notes` 会标明）。
- **`CFO/CFI/CFF`**：覆盖「所用現金淨額」「所產生（所用）」、带空格的「投資活動 (所用) 所得」、以及「經營活動現金流入/流出淨額」。
- **`TBL_BS`**：`資產總值` → `TOTAL_ASSETS`；`負債總值` → `TOTAL_LIAB`；`虧絀總額` / 應佔虧絀 → `NET_ASSETS`（可为负）。`資產總值減流動負債` 仍由行名黑名单拒绝。
- 拆格行名（「應佔年內」+「全面虧損總額」）会拼格后再匹配。

### 2.5 检索包契约（`retrieve_finance` 依赖）

财务 Agent **不自己切表**，只消费 `retrieval` 整表包（`evidence_by_table`）。改表名/跨页门控后必须 **重建检索包**（批量不要加 `--skip-retrieval`）。不为单家发行人写 profile，别名表吸收写法差异。

配置：`retrieval/configs/agent_retrieval_profiles.yaml`；展开：`retrieval/src/retrieval/evidence_expand.py`。策略说明：[`retrieval/configs/finance_table_retrieval_strategy.md`](../../retrieval/configs/finance_table_retrieval_strategy.md)。

| 表 | 18A 易漏写法（已吸收进通用别名） |
|----|----------------------------------|
| `TBL_IS` | `綜合全面虧損表` / `合併損益及其他綜合收益表`；税前虧損、年／期內溢利(虧損) |
| `TBL_BS` | `綜合資產負債表`（不仅「財務狀況表」）；`資產總值` ∧（`權益總額` / `虧絀總額` / `負債總值`） |
| `TBL_BS_COMPANY` | `貴公司財務狀況表` **或** `本公司資產負債表`；不并入集团 BS pack |
| `TBL_CF` | 经营页 + 投资/融资续页；续页含「投資活動/融資活動」不得误判为损益表；行名可带空格括号或拆行 |

`must_have_groups`：组内 OR、组间 AND。CF 投资/融资组对「投資活動 (所用) 所得現金淨額」等做宽松匹配。

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

理想路径约 7–8 轮：`retrieve → skill×5 →（可选 search）→ run_rule_checks` → **`prefer_llm_submit` 再叫一轮真正的 `submit_legal_report`**（写 summary/reasoning；`risk_points` 可空由系统从 skill 填充）。LLM 终裁失败 / `max_turns` 耗尽才 `_auto_submit_if_ready` 托底。默认 `max_turns=10`。

自动收束：至少 2 个 skill 后，用 `_structured_legal_auto_summary` 按 skill 汇总风险点（code / level / 页码），**禁止**空模板摘要；`submit_warnings` 记 `auto_submit:{reason}`。

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
- 上述 `*_pct` 字段均采用**百分比点**口径：结构化 JSON 中 `12.5` 表示 12.5%，不是 0.125。Markdown 报告统一追加 `%`，且不会把 12.5 错格式化为 1250%；同一规则适用于客户/供应商集中度的 `top1_*_pct` / `top5_*_pct`。

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
  → LLM 终裁失败 / 轮次耗尽：服务端 _auto_submit_if_ready 托底（结构化摘要）
  → submit 定稿：规则托底 → 18A DATA_INSUFFICIENT → 叙事对齐 → DebateDossier 落盘
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
  → LLM 终裁失败 / 轮次耗尽：服务端 _auto_submit_if_ready 托底（_structured_legal_auto_summary）
  → point_kind + 饱和聚合 → DebateDossier
```

### 4.3 Think 状态标签

| 标签 | 含义 |
|------|------|
| `ok` | 有 `message.reasoning` |
| `think_from_content` | 无 reasoning，但有 content / tool.reason；**不**触发 missing-think 重试 |
| `reasoning_missing` | 缺 think；整场首次 nudge 重试一次 |
| `reasoning_missing_after_retry` | 重试后仍缺；工具照常执行 |

Token：专家 ReAct 中间轮 `max_tokens=2048`，收束/submit `4096`。DeepSeek 思考计入 `max_tokens`：调用方的 `max_tokens` 视为正文预算，另加 `reasoning_max_tokens`（总控 JSON 步默认 512）。空 JSON / `finish_reason=length` 时 `llm_json` 会放大预算并重试，最后一轮关掉 thinking。`provider=vllm` 不发 DeepSeek `thinking`。

### 4.4 并行出口

`src/graph/parallel.py`：`--agent all` 走 `run_finance_legal_market_parallel`——财务 ‖ 法务 ‖ 市场 **三专家并行探查**，`asyncio.gather` 齐了再 `merge_results` 进总控。对照分按 `configs/master_rules.yaml` 权重计入市场情绪风险贡献。总控子图在 `src/graph/master_graph.py`（专家探查不进该图）。市场失败写 `market_error`，不阻断财务/法务/总控。

```json
{
  "doc_id": "...",
  "finance": { "...AgentResult" },
  "legal": { "...AgentResult" },
  "market": {
    "...AgentResult": "...",
    "risk_score": 60.0,
    "features": {
      "scoring_mode": "historical_rules_floor|llm",
      "deterministic_score": 59.4,
      "llm_score": 60,
      "sentiment_analysis": { "overall_net_support": -0.129 }
    }
  },
  "market_error": null,
  "market_reference_score": 56.45,
  "market_reference_score_meta": { "source": "market_risk_score", "overall_net_support": -0.129 },
  "reference_fundamental_score": 64.18,
  "cross_agent_features": [],
  "master": {
    "judgment": { "overall_score": 70, "level": "high", "risk_level_http": "HIGH" },
    "predicted_windows": { "ipo_day_break_risk": "high", "...": "..." },
    "price_path_forecast": [{ "window": "D1", "risk_label": "high", "...": "..." }],
    "post_listing": { "status": "completed|partial|not_available", "weighted_hit_score": 82.5, "...": "..." }
  },
  "note": "对照加权分 vs 总控终裁；有市场结果时计入原生 market_risk_score 权重"
}
```

`reference_fundamental_score`：先算基本面 `legal×0.55 + finance×0.45`，有真实市场结果时再合成 `(基本面)×0.65 + market.risk_score×0.35`（权重见 `configs/master_rules.yaml`）。`risk_score` 是市场 Agent 经历史规则底线与 LLM 证据评估合并后的 0–100 首日破发风险分，因此作为总控对照分的市场输入。`features.sentiment_analysis.overall_net_support` 范围为 `-100%..+100%`（实现中通常为 `-1..+1`），只描述多空方向，连同整体状态和市场证据交给总控综合研判，不参与机械换算。无市场结果时不掺占位分。**正式等级与顶层 HTTP `riskLevel` 以总控终裁为准。** `--skip-master` 可回到 `master=null`。市场失败时 `market=null` 且写入 `market_error`，财务/法务/总控仍出结果。

---

## 5. 中间结果与最终产物

### 5.1 上游输入（本仓消费）

| 输入 | 典型路径 |
|------|----------|
| `full_parse.json` | `pdf_parsing/output/.../full_parse.json` |
| 财务检索包 | `retrieval/.runtime/agent_retrieval_{doc_id}_finance.json` |
| 法务检索包 | `retrieval/.runtime/agent_retrieval_{doc_id}_legal.json` |

HTTP 路径下由 9101 prepare 生成；CLI 可离线 JSON 或 `--use-live-retrieval`。改了 `agent_retrieval_profiles.yaml` / `evidence_expand.py` 后须重建检索包，否则 Agent 仍吃旧整表证据。

### 5.2 Agent 运行中

| 产物 | 路径 / 位置 |
|------|-------------|
| 推理日志 | `logs/{doc_name}_{finance\|legal\|market\|master}_{ts}.log` + `.jsonl` |
| ReAct state | 内存：`skill_results` / `metrics` / `queries_used` / `rule_pack` |
| HTTP SSE | `.runtime/analyses/{analysisId}/events.jsonl`（thought / agent_status / agent_report / phase_change / debate_* / report_ready / analysis_complete） |

### 5.3 交卷后

| 产物 | 路径 |
|------|------|
| 合并结果 JSON | `.runtime/{name}_finance_legal*.json`（文件名沿用；内含 `finance` / `legal` / `market` / `master`） |
| 财务 / 法务 / 市场 dossier | `.runtime/debate/{doc_id}_{finance\|legal\|market}_dossier_{ts}.json` |
| 总控 dossier | `.runtime/debate/{doc_id}_master_{ts}.json`（含 `judgment`、`price_path_forecast`、`post_listing`、`debate_history`、`report_markdown`） |
| 四份 MD | `reports/{五位代码}_finance_report.md` / `_legal_report.md` / `_market_report.md` / `_ipo_risk_warning_report.md` |
| HTTP result | `.runtime/analyses/{analysisId}/result.json`（`agents.*.reportMarkdown` 三份独立；含 `debate` / `report`） |
| HTTP 总控报告 | `.runtime/analyses/{analysisId}/report.json` ≡ `GET .../report`；含 `pricePathForecast` / `postListingValidation`，PDF 由同一 ReportData 渲染 |

HTTP 终态发布顺序是强契约：先写专家/总控 MD 与 `report.json`，再写完整 `result.json`，随后以不提前唤醒 SSE 的方式将 meta 更新为 `status=completed, phase=report`，最后才写入并广播 `report_ready`。因此客户端收到 `report_ready` 后可立即读取 `/analysis/result` 与 `/report`，不会再出现“事件已到但报告接口短暂 404”的窗口。

### 5.4 AgentResult 关键字段

- `risk_score` / `risk_level` / `summary` / `score_breakdown` / `risk_points`
- 财务 `score_breakdown[].metric_value`（可计算原值）/ `metric_display`（报告展示值）
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
  --stock-code 03378 \
  --finance-retrieval /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_finance.json \
  --legal-retrieval /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_legal.json \
  --reports-dir reports
# 产出 reports/03378_finance_report.md / 03378_legal_report.md / 03378_market_report.md
#      reports/03378_ipo_risk_warning_report.md（有 master 时）
# --out 已废弃：若仍传入，目录当作 --reports-dir，文件则取其父目录
```

### 6.5 已解析 JSON 的完整 CLI 链路

对已有 `full_parse.json`，完整顺序固定为：

```text
build_index_from_parse.py
  → simulate_agent_retrieval.py --agent finance
  → simulate_agent_retrieval.py --agent legal
  → run_finance_legal.py --agent all
       （finance ‖ legal ‖ market → master）
  → generate_analysis_report.py
       （finance / legal / market / ipo_risk_warning 四份 MD）
```

建议每次验证使用独立 `doc-id`、结果文件和 `reports-dir`，避免覆盖历史运行。索引命令中的 `listing-date` 是实际上市日，不是招股书文件名日期；`issuer-type=general` 会跳过 18A/18C 专属财务与法务管线。

---

## 7. CLI 参数详解

入口：`scripts/run_finance_legal.py`

| 参数 | 说明 |
|------|------|
| `--agent` | `finance` / `legal` / `market` / `all`（默认三专家并行后接总控） |
| `--stock-code` | 市场 Agent 港股代码；未传时从 `--pdf-name` 开头识别；`market`/`all` 必须“显式传入或成功识别” |
| `--skip-master` | 专家探查后不跑总控（旧行为 `master=null`） |
| `--skip-embellishment` | 关闭文本粉饰度分析（默认开启）；关闭后不调用粉饰模型、不参与终裁 Prompt/门控，所有报告省略该章节 |
| `--skip-experts` | 跳过财务/法务/市场探查，直接总控；必须配合 `--from-result` |
| `--from-result` | 已有专家 merged JSON（含 `finance`/`legal`） |
| `--master-provider` / `--master-chat-model` | 覆盖总控模型；默认与专家共用同一 `LLMClient` |
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

### 8.1 财务 + 法务 + 市场 + 总控（推荐）

`pdf-name` 以 `03378` 开头时可省略 `--stock-code`；显式传入更稳。**CLI** 对 `--agent market/all` 做前置校验：既未传 `--stock-code`、也无法从 `--pdf-name` 开头识别代码时会直接报错，不会降级运行。只有 **HTTP 9102** 链路在缺少股票代码时把市场标为 `skipped`，改走财务 ‖ 法务并行后接总控。

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk

python scripts/run_finance_legal.py \
  --agent all \
  --stock-code 03378 \
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

### 8.4 跳过专家、只跑总控（复用已有 JSON）

```bash
python scripts/run_finance_legal.py \
  --agent all --skip-experts \
  --from-result .runtime/hansiaitai_finance_legal_market.json \
  --doc-id hansiaitai \
  --doc-name 翰思艾泰 \
  --pdf-name "03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf" \
  --parse-json "/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/03378_15-12-2025_翰思艾泰－Ｂ_全球發售/full_parse.json" \
  --provider deepseek \
  --chat-model deepseek-v4-flash \
  --out .runtime/hansiaitai_master.json \
  --log-dir logs

python scripts/generate_analysis_report.py \
  --result .runtime/hansiaitai_master.json \
  --doc-name 翰思艾泰 \
  --pdf-name "03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf" \
  --stock-code 03378 \
  --finance-retrieval /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_finance.json \
  --legal-retrieval /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_legal.json \
  --reports-dir reports
# 产出 reports/03378_finance_report.md / 03378_legal_report.md / 03378_market_report.md
#      reports/03378_ipo_risk_warning_report.md（总控预警报告，含走势预判和上市后验证）
```

加载日志应含市场分，例如 `finance=75.0 legal=60.9 market=62.0`。未传 `--doc-name` 会落到默认「蜜雪集團」。`--parse-json` 供粉饰全书扫描/章节定位、原文页码回查及辩论页码直取。`--skip-embellishment` 可在复用专家结果时一并使用；它不等同于分析失败，也不会降低总控置信度。`--skip-experts` 与 `--skip-master` 互斥。

### 8.5 近期联调快照

| 产物 | 分数 | 说明 |
|------|------|------|
| `.runtime/hansiaitai_master_improved_no_embellishment_v3_20260821.json` | 财务 **75.0** / 法务 **60.9** / 市场 **61.0** / 对照分 **65.06** / 总控 **63.0 HIGH** | `degraded=false`；改进后辩论 2 轮；财务补出赎回压力跑道 1.55 个月；市场完整复现 59.4/61.0 评分血缘；粉饰分析主动关闭 |
| `reports/hansiaitai_master_improved_no_embellishment_v3_20260821/` | 四份 Markdown | 总控报告不含粉饰章节；市场净支持率 -12.9% 仅作方向描述，不参与 0–100 风险分机械换算 |
| 蜜雪 `test_batch` 全链路（2026-08-20） | 财务 **0.0** / 法务 **28.8** / 市场 **43.7** / 总控 **35.0 MEDIUM** | `.runtime/mixue_02097_testbatch_20260820_fullflow.json`；`degraded=false`，辩论 2 轮，上市后 D1/D5/D20/D60 验证完成，四份报告在 `.runtime/mixue_02097_testbatch_20260820_reports/` |
| 蜜雪系统修复最终回归（2026-08-22，关闭粉饰） | 财务 **0.0** / 法务 **22.2** / 市场 **43.7** / 对照分 **23.23** / 总控 **43.7 MEDIUM** | `.runtime/mixue_02097_system_fix_final_no_embellishment_20260822.json`；`degraded=false`，辩论 2 轮；市场首轮 `verified` 并给出数值/证据 ID，财务答辩携带财务表页码；四份报告在 `reports/mixue_02097_system_fix_final_no_embellishment_20260822/` |

---

## 9. 总控决策 Agent

总控是默认主链路，不是规划项。`--agent all` 与 HTTP 9102 都在三专家探查之后跑 `MasterAgent`。专家探查（财务/法务 ReAct、市场 ReAct）**不进**总控子图。

```
三专家并行探查（finance ‖ legal ‖ market）
        ↓  merge_results：对照分 + 压卡片
   MasterAgent / master_graph
        ├─ detect_conflicts     冲突研判 JSON
        ├─ [need_debate?] run_debate
        ├─ [enabled?] score_embellishment  全书候选扫描 + 风险因素完整复核
        ├─ master_decide        终裁 JSON（0–100）+ D1/D5/D20/D60 走势预判
        ├─ validate_postlisting_performance
        └─ generate_warning_report
        ↓
   master.judgment + price_path_forecast + post_listing + *_master_*.json + report_markdown
```

| 组件 | 职责 |
|------|------|
| `src/agents/master_agent.py` | 编排入口：压卡片、跑子图/顺序 pipeline、落盘 dossier |
| `src/graph/master_graph.py` | LangGraph：`detect → (debate?) → embellish → decide → validate_postlisting → report`；图构建或执行异常时 `MasterAgent` 按同序节点降级为顺序执行 |
| `src/skills/master_cards.py` | dossier → 短卡片；对照分 `legal×0.55+finance×0.45`，有市场再 `×0.65+market.risk_score×0.35`；净支持率仅作综合研判信息 |
| `src/skills/detect_conflicts.py` | 研判 `resonance` / `conflict` / `evidence_gap` |
| `src/skills/run_debate.py` + `debate_reply.py` + `debate_query.py` | 条件辩论与补证检索 |
| `src/skills/score_embellishment.py` | 第四章粉饰 0–10：全书规则扫描、风险因素优先、候选原文回查与规则计分 |
| `src/skills/master_decide.py` | 终裁 + 结构化走势预判；漏用第五章高风险清单则 LLM 再修订一次 |
| `src/skills/validate_postlisting_performance.py` | 对齐 D1/D5/D20/D60 上市前预测与真实检查点，计算命中分 |
| `src/skills/generate_warning_report.py` | 把终裁、走势预判、上市后验证排成 Markdown，不另起结论 |
| `configs/master_rules.yaml` | 第五章清单、对照权重、辩论/终裁 token、主题检索词表 |
| `--skip-experts --from-result` | 复用已有 merged JSON 只跑总控；`finance` / `legal` 必需，`market` 可选 |
| `--skip-master` | 专家探查后 `master=null` |
| `--skip-embellishment` | 仅关闭粉饰分析，总控及三专家仍正常执行；默认不传即开启 |

总控是 **LLM Agent**，不是规则引擎。规则只做：压卡片、把第五章清单写入 Prompt、JSON 全失败时 `degraded` 托底。Python **不直接改** `riskLevel`（含 `gate_warning` 后也不改）。禁止 `if qwen: skip_master_llm`。HTTP 上 `map_master_event` 把总控 **实时事件** 映射为 `agentId=orchestrator` 的 Thought（`StreamHub` 立刻推 SSE；**禁止**跑完后再回放 jsonl）。辩论补证/作答走 `map_debate_expert_event`，记到专家 `agentId`，不记成 orchestrator。

对照分 `reference_fundamental_score` 只作参考，**正式等级与顶层 HTTP `riskLevel` 以终裁为准**。市场 Agent 的 `risk_score` 是 0–100 首日破发风险分，并作为对照分的市场输入；`overall_net_support`（`-100%..+100%`，正数支持、负数不支持）作为独立的方向指标交给总控综合研判。

市场参与总控分为三层：卡片在冲突检测与终裁阶段始终参与；检测到市场与财务/法务结论冲突、市场证据缺口或需要解释市场分与净支持率分化时，可在辩论中点名 `market`；若模型漏掉已识别的真实市场议题，编排器会补入一条市场质询。市场回复由 `MarketAgent.respond_to_controller` 按 `MARKET_DEBATE_REPLY` 生成，并可使用本地上市前证据补证。答辩上下文固定携带 `deterministic_score`、`llm_score`、`score_reconciliation`、`prelisting_day1_risk`、`sentiment_analysis.overall_net_support` 与证据账本，故补证检索零命中也不得否认已审计评分血缘。

评测（Qwen3.6 35B + vLLM）与开发（DeepSeek）走同一套步骤：

```bash
python scripts/run_finance_legal.py --agent all \
  --provider vllm --api-base http://<评委>:8000/v1 --chat-model <Qwen3.6-35B>
```

`provider=vllm` 允许空 API key，payload 不发 DeepSeek `thinking`。无 key 的开发机才会规则降级（`master.degraded`），不阻断出分。

### 9.1 冲突研判（是否开辩）

输入：三路短卡片 + 对照分 + 第五章清单。输出必须同时有 `conflicts` 与 `need_debate`。空 JSON / 思考占满预算 **不得**当成「无冲突、不开辩」：标 `degraded`，正文预算 2048 + 思考预留 512，失败则放大预算并关 thinking 重试。

`conflicts[].kind`：

| kind | 含义 | 是否开辩 |
|------|------|----------|
| `conflict` | 两路主张打架（金额/期限/是否已清理对不上） | 应 `need_discussion=true` → 开辩 |
| `resonance` | 同向印证，例如财务 `CV_PREF_LIABILITY` 与法务 `REDEMPTION_HIGH` 同指一笔赎回负债 | **不是冲突**；是否写入 `conflicts` 并由 `need_discussion` 开辩，由模型当轮决定 |
| `evidence_gap` | 主张缺少其职责对应的可核验证据：财务/法务通常为招股书页码，市场为数据源、字段、证据 ID、截止日与数值 | 可开辩补证 |

职责分轨（与 §1 / §9.4 一致）：现金跑道只归财务；集中度/关联交易打分只归法务；赎回**条款**归法务、**表内负债**归财务，同向是共振不是打架。市场卡片参与研判，无交叉矛盾时不必点名市场。

工程开辩条件：`need_debate=true` **或** 任一条 `need_discussion=true`。纯共振且模型写 `conflicts=[]` 时会跳过辩论，直接粉饰、终裁（翰思艾泰 2026-08-17 15:06 那次即此）。

### 9.2 条件辩论

最多 **3** 轮；每轮问题一次性打包并行（cap **4**）；可问 `finance` / `legal` / `market`（各自 `respond_to_controller`）。答完再判是否追问。辩论 **不会** 重跑专家 ReAct / `submit_*_report`。

专家答辩以各自已经提交的 `AgentResult` 为第一证据源，standalone 检索只负责补证：`parallel.py` 在专家完成或 `--skip-experts --from-result` 恢复后，将结果绑定到专家实例的 `_last_result`。财务上下文携带 `metrics`、打分项、`evidence_summary.table_meta`（`TBL_IS` / `TBL_BS` / `TBL_CF` 等表格页码与摘录）和自动计算的极端赎回敏感性情景；法务携带打分项、风险点、3.x 专项结果及证据摘要；市场携带完整评分血缘与上市前证据账本。不得因本轮检索零命中而把这些既有字段改口为“未披露”。

证据契约按职责分轨：财务/法务分析招股书，质询可要求对应页码；市场分析外部上市前时点数据，不应被要求提供招股书页码。市场质询由编排器规范为 `market_field` / `evidence_id` / `as_of_date` / `value` 等要求，并移除页码提示。市场 EvidenceRef 合法使用 `page=null`，同时携带 `field_code=evidence_id` 以及字段、数值、截止日和解释。

质询 JSON 可带 `search_hints: {pages, keywords}`；不填则规则抽取。追问轮同样。

补证检索（`src/skills/debate_query.py`，词表在 `master_rules.yaml` → `debate.debate_search`）：

1. **质询文本只给人读，不进 BM25。** 禁止把「請財務總監…」整段当 query。
2. **财务/法务页码直取优先**：从质询/卡片/`search_hints` 抽页（如第 497/563 页）→ `hits_from_prefer_pages`；财务表类质询还会从 `table_meta` 恢复主表页码。
3. **财务/法务短关键词其次**：金额、主题词（`贖回負債` / `購回權`）、code 词表；`query_max_chars=32`。市场改查本地上市前特征/新闻，并与已审计 `evidence_catalog` 合并。
4. 脏命中（不在指定页、无关键词）不算成功，打满每问 ≤2 次配额。
5. 回答前同时注入「己方已审计结果上下文」「己方 claim 已有证据」和 claim 卡片；卡片或 AgentResult 已写明的金额、页码、公式与评分中间值不得改口成未披露。
6. 财务若已有 `END_CASH`、`BURN_RATE_MONTHLY` 与 `CV_PREF`，自动附加极端情景：即时全额现金赎回、无新增融资或流入；输出剩余现金与压力跑道，并明确其为敏感性分析而非招股书预测。
7. 答复提交前有一致性门控：若声称现金字段或市场评分构成缺失，而审计上下文实际存在，则追加校正并限制状态/置信度，避免错误的 `verified`。
8. 市场已有至少两条结构化上下文证据时，不得仅因 `page=null` 或 standalone 零命中维持 `unresolved`；模型 JSON 截断时会从证据账本生成包含 evidence ID、字段值与截止日的实质回复，并以 `partially_accepted` 兜底。

Standalone 入口：`search_finance_evidence_standalone` / `search_legal_evidence_standalone`（均可 `prefer_pages`）以及市场 `search_market_evidence_standalone`。空有效 hits 仍须发言；若 claim 卡片和已审计上下文也无证据，则 `confidence≤0.4` 且禁止 `verified`、禁止编造页码。若已审计上下文有值，必须引用该值并把“本轮未新增命中”与“原结论无证据”区分开。

每轮结束后，`_round_digest` 向追问模型保留每条回复前 **1200** 字、status、confidence、命中数和证据页；这是为避免关键算式位于回复后半段而被误判为“尚未计算”。

### 9.3 粉饰与终裁

粉饰：默认启用，采用“全书规则扫描 + 重点章节深度分析”，0–10（low/medium/high），不替代终裁。CLI 可传 `--skip-embellishment`，HTTP 可传 `enableEmbellishment=false` 主动关闭。关闭会跳过 `ScoreEmbellishmentSkill`，从终裁 Prompt 与 `EMBELLISHMENT_HIGH` 门控中移除粉饰输入，并在结果中记录 `analysis_options.embellishment_enabled=false`、`master.embellishment=null`；主动关闭不会按 `not_available` 处理，也不会作为证据缺失降低置信度。前五页只判断首页营销与信息后置；风险因素章节完整扫描，概要、业务、行业概览用于发现宣传/排名/概念候选，财务资料和财务/法务卡片用于核验量化支撑与风险弱化。普通法定风险措辞不单独计分。

粉饰结果保留兼容字段 `score/level/reason/hits/dimensions`，并新增 `status`、`coverage`、`high_risk_excerpts`、`limitations`。LLM 只能判断程序生成的 `candidate_id`；正式页码和原文由 `full_parse.json` 回填。无法回查的引用不会进入报告；解析或模型复核不完整时为 `partial/not_available`，不得解释为低粉饰。

粉饰度是**总控专项研判**，不是财务、法务或市场 Agent 的结论。终裁若把“文本粉饰度高”列为风险因子，`source_agent` 必须为 `master`，证据必须引用 `high_risk_excerpts` 中已核验的 PDF 页码和原文；“10/10（high）”等分数或等级标签不能作为原文证据。报告生成器会兼容修正旧结果中的错误归属，并优先绑定已核验切片。

终裁 `master_decide`：

- 输入用**压缩辩论摘要**（轮次 / status / confidence / 证据页 / 回复摘要），不把 evidence HTML 全文塞进 prompt；轮间追问的 `_round_digest` 每条回复保留前 **1200** 字，终裁的 `compact_debate_digest` 则进一步压到每条回复前 **280** 字（并保留问题、状态、置信度、命中数和证据页）。
- 正文预算 **4096** + 思考预留 512；必须同时有 `overall_score`（**0–100**，禁止 0–1）和 `level`。
- 终裁 JSON 同时输出 `predicted_windows`（标签兼容）和 `price_path_forecast`（D1/D5/D20/D60 结构化走势预判）。走势预判必须是**上市前业务判断**，禁止引用上市后真实表现、复盘字段或 outcome 数据；不写具体目标价或精确收益率，除非输入证据已有可量化模型支持。
- `price_path_forecast` 若缺失或缺窗口，服务端按 `predicted_windows` 补默认 D1/D5/D20/D60 文案，保证后续验证链路字段完整。
- JSON 三次仍空：`degraded=true`，规则托底对照分 + 第五章高风险码 → `high`，置信度 low。这不是正式终裁。
- 第一次给出 `level=low` 但卡片含 `CASH_RUNWAY_LT_12` / `REDEMPTION_HIGH` / `CONCENTRATION_HIGH` / `VALUATION_INVERSION`：发 `gate_warning`，**再让 LLM 修订一次**；Python 不改等级。

上市后验证 `validate_postlisting_performance`：

- 总控 `decide` 后、`report` 前自动执行；输入 `stock_code`、`predicted_windows`、`price_path_forecast`。
- 优先读取 `configs/market_agent.yaml` 的 `output.postlisting_json_filename`，现行为 `{doc_id}_{stock_code}_postlisting.json`；也兼容 `{doc_id}_postlisting.json`。显式 `postlisting_json` 可覆盖。
- 无 JSON 时尝试从 `data.postlisting_checkpoints_csv` 通过 `PostlistingRiskScorer` 评分生成 D1/D5/D20/D60；仍失败则 `status=not_available` 并记录 `limitations`。
- 窗口权重固定：D1 0.30、D5 0.35、D20 0.20、D60 0.15。`weighted_hit_score` / `business_value_score` 为已对齐窗口的加权命中分；`d5_priority_hit` 只在 D5 预测为 high 且真实显著下行时为 true。
- 真实严重度规则：低于发行价、开盘基准累计收益≤-10%、最大回撤≤-15% 或真实风险分≥70 → `severe`；累计收益≤-5%、最大回撤≤-10% 或真实风险分≥50 → `moderate`；其余 `benign`。

报告分层：

- 总控 `generate_warning_report` 排版终裁 JSON、走势预判和上市后验证，写入 dossier / `result.report` 的摘要来源，**不**拼进三份专家 MD。
- `scripts/generate_analysis_report.py`（CLI）或 HTTP runner 会写专家三份独立报告：`{代码}_finance_report.md` / `_legal_report.md` / `_market_report.md`；有 `master` 时额外写 `{代码}_ipo_risk_warning_report.md`。
- 总控报告的辩论证据按职责显示：财务/法务使用“证据页”，市场使用“市场证据：<evidence_id...>”，不会把市场的 `page=null` 渲染成缺少招股书页码。
- 启用粉饰分析时，CLI 总控预警报告包含独立“文本粉饰度专项分析”章节，展示五维评分、覆盖范围及经原文回查的 Top 10 高等级切片；HTTP `report.embellishmentAnalysis.highRiskExcerpts` 返回全量，PDF 同样展示 Top 10。关闭时 Markdown/PDF 不生成该章，ReportData 同时省略粉饰维度和 `embellishmentAnalysis`，后续章节自动连续重编号。
- 报告中的 HTML 表格切片会先清理为安全纯文本，避免不完整的 `<table>/<tr>` 把后续 Markdown 吞入表格。
- CLI 总控预警报告会把长段预测/验证拆成「预测要点」「主要触发依据」「验证摘要」「预测文本」「行情指标」等 bullet，并清理 JSON 字段自带句尾标点，避免 `。；` / `。。`。
- 前端综合页走 `GET .../report`（ReportData JSON，与 `result.report` 同一对象）和 `GET .../report/export`（PDF）。ReportData 透传 `pricePathForecast` / `postListingValidation`，启用时以可选字段 `embellishmentAnalysis` 返回粉饰状态、覆盖范围、五维分项及全量高等级原文，并在 `dimensions` 保留粉饰汇总分；关闭时这两处均省略。

### 9.4 Dossier

```text
DebateDossier（专家探查结束即落盘，有无辩论都有）
  risk_score / risk_level / summary / reasoning
  claims[]: code, level, statement, evidence_refs[], retrieval_queries[]
  retrieval_queries[] / negative_findings / rule_flags
```

路径：`.runtime/debate/{doc_id}_{finance|legal|market}_dossier_{ts}.json`

总控：`.runtime/debate/{doc_id}_master_{ts}.json`（`conflicts`、`debate_history`、`judgment`、`price_path_forecast`、`post_listing`、`embellishment`、`report_markdown`）

读写：`save_dossier` / `load_dossier`。`.runtime/debate/` 下的专家 dossier **不是**辩论记录。

### 9.5 跨 Agent 主题表

清单：`configs/master_rules.yaml`；主题码提示：`src/skills/master_cards.py` 的 `THEME_CODE_HINTS`。

| 主题 | 财务 | 法务 | 市场 | 总控怎么判 |
|------|------|------|------|------------|
| 赎回/优先股 | `CV_PREF_LIABILITY` 表内负债 | `REDEMPTION_*` / `RIGHTS_CLEANUP_*` | 不负责条款 | 同向=共振（交叉印证，不是打架）；表内重大 vs 已清理=冲突 |
| 现金跑道 | `CASH_RUNWAY_*` / `BURN_YOY_*` | 不计分 | 不负责跑道 | 财务单方硬门控，非法务缺席 |
| 客户/供应商集中 | 只解释钱，不打 CONCENTRATION | `CONCENTRATION_*` | — | 非法务缺席 |
| 关联交易占比 | 不做独立占比打分 | `RELATED_PARTY_*` | — | 同上 |
| 首日破发/板块 | — | — | `day1_break_risk` 等 | 与基本面无交叉矛盾则不必开辩 |
| 文本粉饰 | 双方均未做 | 双方均未做 | — | **总控粉饰 Skill**（默认在终裁前运行，可显式关闭） |

---

## 10. 前端相关：端口 / 输入输出 / HTTP

### 10.1 端口拓扑

```
前端 ──► :9100（解析网关 + 反代分析；唯一 Base）
           ├─ parse / index-status              （本机）
           ├─ GET /api/v1/agents/status         ──反代──► :9102
           ├─ analysis/start|stream|result      ──反代──► :9102
           ├─ report | report/export            ──反代──► :9102
           └─（内部）9101 检索 prepare / artifacts
```

| 端口 | 服务 | 前端是否直连 |
|------|------|--------------|
| **9100** | 解析 + 网关 | **是**（唯一 Base） |
| **9101** | 检索 | 否 |
| **9102** | 财务/法务/市场分析 + 总控（本仓） | 否（经 9100 反代） |

前端配置：只设 `VITE_API_BASE=http://<host>:9100`，**不要**配 9101/9102。

### 10.2 本仓暴露的 HTTP 路由（9102）

契约：[`dataset/interface_protocol_v3.4.md`](../../dataset/interface_protocol_v3.4.md)。前端只打 **9100**；9102 被网关原样反代。总控 **无** 独立 `/master/start`。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` 或 `/api/v1/health` | 探活 |
| GET | `/api/v1/agents/status` | 四 Agent `ready`（不在 `/projects` 下） |
| POST | `/api/v1/projects/:id/analysis/start` | 启动分析 → **202** `{analysisId, status}` |
| GET | `.../analysis/stream?analysisId=` | SSE：见 §10.4 |
| GET | `.../analysis/result?analysisId=` | 完整结果或进行中快照（含 `phase` / `debate`） |
| GET | `.../report` | ReportData JSON；分析未完成 → **404**；≡ `result.report` |
| GET | `.../report/export` | PDF 二进制；`Content-Disposition: IPO风险报告_{ticker}_{date}.pdf` |

不实现已删除的 `/rag/query`、`/parse/quick`、bbox `/evidence`。运维逃生口 `GET /capacity`（在 9100）、解析 `result/content.md` 不写入前端契约。

实现：`service/app.py`、`service/routes_analysis.py`、`service/analysis_runner.py`、`service/thought_mapper.py`、`service/report_data.py`、`service/report_pdf.py`。

法务 Thought 映射（`map_legal_event`）与财务对齐：消费 pipeline 顶层 `evidence_hits`、工具 `output.hits`/`evidence`、以及 `output.risk_points`；ReAct 默认 `translate_think=True`（繁中展示 + `meta.rawThink`）。辩论补证/作答走 `map_debate_expert_event`（记到专家 `agentId`，禁止记成 orchestrator）。

### 10.3 start 输入

```json
{
  "clientProjectId": "proj-xxx",
  "taskId": "task_expert_...",
  "ticker": "03378.HK",
  "llmConfig": {
    "apiBaseUrl": "https://api.deepseek.com",
    "apiKey": "sk-...",
    "model": "deepseek-v4-flash"
  },
  "isBiotech": true,
  "enableEmbellishment": true
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `clientProjectId` | 是 | 与路径一致 |
| `taskId` | 建议 | 关联解析任务；用于找 meta / 检索包 |
| `ticker` | 建议 | 港股代码，允许 Wind 格式（`03378.HK`）；市场 Agent 优先用此字段 |
| `stockCode` | 否 | `ticker` 的别名 |
| `llmConfig` | 否 | 覆盖后端默认模型 |
| `isBiotech` | 否 | 覆盖发行人类型 → `biotech` / `general`；`true` 与 CLI `18a`/`18c` **门控等价** |
| `enableEmbellishment` | 否 | 是否启用文本粉饰度分析，默认 `true`；传 `false` 时跳过分析及门控，并从 Markdown/JSON/PDF 移除粉饰章节/字段 |

前置：解析任务存在且 `indexStatus=ready`，否则 **409** `INDEX_NOT_READY`。

股票代码优先级：`body.ticker` / `body.stockCode` → 解析 meta 的 `stockCode`/`ticker`；规范化为五位数字（`03378.HK` → `03378`）。缺失则市场 Agent `skipped`。

服务端解析 meta 后实际使用：

- `parseJsonPath` → `full_parse.json`
- `retrieval/.runtime/agent_retrieval_{taskId}_{finance|legal}.json`（或 9101 artifacts）
- `issuerType` / `companyName` / `fileName`
- `stockCode` / `ticker`（可被 start body 覆盖）

### 10.4 stream / result 输出

**SSE 事件**

| 事件 | 数据要点 |
|------|----------|
| `agent_status` | `{agentId, status}`：`running` / `completed` / `skipped`；**仅辩论期**可加 `category` |
| `thought` | `{thought: Thought}`：初评/detect/粉饰/终裁 **无** `category`；仅 `phase=debate` 时带 `category=finance\|legal\|market\|master` |
| `phase_change` | `{phase}`：`debate`（条件开辩）/ `report` |
| `agent_report` | 谁先完成谁发，`{agentId, reportMarkdown, agentResult}`，无 `category` |
| `debate_message` | `{message}`：**仅实际开辩**；带 `category` |
| `debate_complete` | `{rounds}`：仅开辩时发送 |
| `report_ready` | `{report: ReportData}`：`report.json`、完整 `result.json` 和 `status=completed` 均已持久化后才发送；收到后可立即请求 `/report` |
| `analysis_complete` | `{overallScore, riskLevel}`：终裁 0–100 |
| `heartbeat` | 约 15s |

三专家 **实时混流**（不再缓冲 financial 到 legal 完成）。总控从 `detect_conflicts` 起以 `agentId=orchestrator` 实时推送（不回放 jsonl）。辩论是条件的：`need_debate=true` 或任一条 `need_discussion=true` 才 `phase_change: debate`；纯共振可跳过（`debate.rounds=0`，stream 无 `category`，不算失败）。无股票代码时 market 为 `skipped`。

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

`analysisOptions.embellishmentEnabled` 明确记录本次是否主动启用粉饰分析；关闭时 `agents.orchestrator.master.embellishment=null`，且 `report` 不含粉饰维度或 `embellishmentAnalysis`。

```json
{
  "analysisId": "...",
  "status": "completed",
  "phase": "report",
  "overallScore": 66,
  "riskLevel": "HIGH",
  "analysisOptions": { "embellishmentEnabled": true },
  "thoughts": [ /* Thought[] */ ],
  "agents": {
    "legal": {
      "agentId": "legal",
      "riskScore": 60.9,
      "riskLevel": "high",
      "summary": "…",
      "reportMarkdown": "…独立法务 MD…",
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
      "reportMarkdown": "…独立财务 MD…",
      "scoringMode": "react+rules_floor",
      "rulesFloor": { "finalScore": 75, "rulesScore": 75, "llmScore": 70 },
      "financeDetail": { "tables": [], "metrics": [], "gates": {}, "cashBurn": null },
      "agentResult": {}
    },
    "market": {
      "agentId": "market",
      "riskScore": 62,
      "riskLevel": "medium",
      "summary": "…",
      "reportMarkdown": "…独立市场 MD…",
      "scoringMode": "historical_rules_floor",
      "marketDetail": {
        "deterministicScore": 62,
        "llmScore": 70,
        "sentimentAnalysis": {},
        "evidenceCatalog": [],
        "debateDossierPath": "..."
      },
      "agentResult": {}
    },
    "orchestrator": {
      "agentId": "orchestrator",
      "status": "completed",
      "overallScore": 66,
      "riskLevel": "HIGH",
      "note": "master_verdict",
      "logText": "…",
      "logEvents": []
    }
  },
  "dossierPaths": { "finance": "...", "legal": "...", "market": "...", "master": "..." },
  "debate": { "rounds": 0, "messages": [], "completedAt": null },
  "report": {
    "overallScore": 66,
    "riskLevel": "HIGH",
    "comparableIPOs": [],
    "pricePathForecast": [
      {
        "window": "D1",
        "riskLabel": "high",
        "expectedDirection": "…",
        "expectedPattern": "…",
        "volatilityView": "…",
        "keyDrivers": ["…"],
        "confidence": "medium"
      }
    ],
    "embellishmentAnalysis": {
      "status": "complete",
      "score": 6,
      "level": "medium",
      "coverage": { "pagesAnalyzed": [], "riskFactorPages": [], "candidateCount": 0, "evaluatedCandidateCount": 0 },
      "dimensions": [],
      "highRiskExcerpts": [
        { "page": 123, "section": "risk_factors", "excerpt": "…招股书原文…", "tactic": "risk_minimization", "scoreContribution": 2 }
      ],
      "limitations": []
    },
    "postListingValidation": {
      "status": "completed",
      "weightedHitScore": 82.5,
      "businessValueScore": 82.5,
      "d5PriorityHit": false,
      "forecastAlignmentSummary": "…",
      "weights": { "D1": 0.3, "D5": 0.35, "D20": 0.2, "D60": 0.15 },
      "checkpoints": [
        {
          "window": "D5",
          "predictionLabel": "medium",
          "actualSeverity": "severe",
          "alignment": "partial",
          "observationDate": "2025-12-31",
          "issuePriceReturn": -0.5006,
          "maxDrawdownFromOpen": -0.4965
        }
      ],
      "limitations": []
    }
  },
  "completedAt": "..."
}
```

要点：顶层 `overallScore` / `riskLevel` 为 **总控终裁**（`HIGH|MEDIUM|LOW`）；`reference_fundamental_score` 仍作对照加权分写入 `agents.orchestrator`，市场项直接使用市场 `risk_score`，净支持率单独供终裁研判。`agents.*.riskLevel` 为 Agent 小写枚举；`rulesFloor` 财务/法务字段不对称。

Thought / EvidenceSnippet 类型见契约（`interface_protocol_v3.4.md`）。

已实现：`GET /api/v1/agents/status`、`GET .../report`（与 `result.report` 同对象）、`GET .../report/export`（PDF）。不实现已删除的 `/rag/query`、`/parse/quick`。总控无独立 HTTP，走 `analysis/stream` 的 `orchestrator`。上市后 D1/D5/D20/D60 验证写入 `postListingValidation`；`comparableIPOs=[]` 暂仍为空对照列表。

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
curl -s "$BASE/api/v1/agents/status" | jq
# 期望 readyCount=4
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
    \"ticker\": \"03378.HK\",
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

# 结果 / 报告 JSON / PDF（均经 9100）
curl -s "$BASE/api/v1/projects/${PROJ}/analysis/result?analysisId=${AID}" \
  -o /tmp/analysis_result.json
curl -s "$BASE/api/v1/projects/${PROJ}/report?analysisId=${AID}" \
  -o /tmp/report.json
curl -s "$BASE/api/v1/projects/${PROJ}/report/export?analysisId=${AID}" \
  -o /tmp/report.pdf
python3 -c "import json;d=json.load(open('/tmp/analysis_result.json'))['data'];print(d['status'],d.get('overallScore'),d.get('riskLevel'),d.get('debate',{}).get('rounds'),len(d.get('thoughts')or[]))"

# 断言法务 stream 含推理 / 工具 / 中段 evidence（page+excerpt）
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk
python scripts/assert_legal_stream_parity.py --result /tmp/analysis_result.json
python scripts/assert_legal_stream_parity.py --events /tmp/analysis_stream.sse
# 离线自检（无需起服务）
python scripts/assert_legal_stream_parity.py --self-check
```

期望：start **202**；stream 三路 thought **实时交错**（财务 thought 不必等法务 `completed`）；初评 / detect / 粉饰 / 终裁 / skip-debate **无** `category`；仅实际开辩才有 `phase=debate` 与 `category`；`debate.rounds=0`（跳过辩论）**不算失败**；result 含三份独立 `reportMarkdown`、`phase` / `debate` / `report`；`report.pricePathForecast` 与 `report.postListingValidation` 存在；`/report` 与 `result.report` 同一对象；`/report/export` 为非空 PDF。

翰思全链路（桩解析 `STUB_MODE=True`，只打 9100，日志在 `tests/e2e_hansiaitai_v34/logs/`）：

```bash
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk
bash tests/e2e_hansiaitai_v34/run_e2e.sh
```

常见错误：索引未好 → **409** `INDEX_NOT_READY`；9102 未起 → 网关 **502** `ANALYSIS_UPSTREAM_DOWN`；`/agents/status` 可降级为 `readyCount=0`。

法务 Thought 单测：`python -m pytest tests/test_legal_thought_mapper.py -q`。

---

## 12. 批量 18A

前置：`pdf_parsing/output/18a_batch/` 已有各公司 `full_parse.json`（见 `batch_summary.json`）。  
脚本对 `status=ok` 名单依次：建索引 → 财务/法务检索包 → `--agent all`（与 §8.1 同参）→ 专家三份独立 MD；有总控结果时同步写总控预警 MD。

`doc_id` 取股票代码（如 `01244`），`issuer-type=18a`。

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk

# 推荐：前 3 家（默认 finance=low / legal=high / max-turns=10）
python scripts/batch_finance_legal_18a.py --n 3

# 前 10 家；索引已存在时不强制重建
python scripts/batch_finance_legal_18a.py --n 10 --no-force-index

# 索引与检索包已就绪，只跑三专家+总控分析 + 专家/总控 MD
python scripts/batch_finance_legal_18a.py --n 5 --skip-index --skip-retrieval

# 从第 4 家起再跑 5 家；单家失败继续
python scripts/batch_finance_legal_18a.py --n 5 --start 3 --continue-on-error

# 只重跑指定代码（忽略 --n/--start 切片；仍按名单顺序）
python scripts/batch_finance_legal_18a.py --codes 09606,09939 --skip-index --continue-on-error
```

改了 `agent_retrieval_profiles.yaml` / `evidence_expand.py` 之后 **不要** `--skip-retrieval`，否则 Agent 仍吃旧检索包。索引可 `--skip-index` 复用。目录名若曾被 CP866 误解码（「全球發售」花成西里尔字母），`parse_stem` 会自动还原。

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
| `--codes` | 空 | 仅跑这些股票代码（逗号分隔，如 `02509,09606`）；设置后忽略 `--n/--start` 切片 |

产物约定：

| 类型 | 路径 |
|------|------|
| 检索包 | `retrieval/.runtime/agent_retrieval_{股票代码}_{finance\|legal}.json` |
| 合并结果 JSON | `.runtime/18a_{股票代码}_finance_legal.json`（文件名沿用；内含 market / master） |
| 专家 / 总控 MD | `reports/{五位代码}_finance_report.md` / `_legal_report.md` / `_market_report.md` / `_ipo_risk_warning_report.md` |
| DebateDossier | `.runtime/debate/{股票代码}_{finance\|legal\|market}_dossier_{ts}.json` |

---

## 13. 测试与目录

### 13.1 单测

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk
python -m pytest tests/test_parallel_market_wiring.py tests/test_skip_experts.py \
  tests/test_master_decide.py tests/test_validate_postlisting_performance.py \
  tests/test_analysis_runner_delivery.py -q

# 更完整的本仓回归：
python -m pytest tests/test_legal_react.py tests/test_legal_thought_mapper.py \
  tests/test_finance_react_skills.py tests/test_finance_submit_recover.py \
  tests/test_related_party_ratio.py tests/test_score_finance_runway_uncertain.py \
  tests/test_net_loss_cf_proxy_and_narrative.py \
  tests/test_extract_aliases_and_years.py \
  tests/test_master_gate_warning.py tests/test_conflict_cards.py \
  tests/test_conflict_json_retry.py tests/test_master_decide.py \
  tests/test_embellishment_prompt.py tests/test_embellishment_reports.py \
  tests/test_debate_trace.py \
  tests/test_debate_cap.py tests/test_debate_query.py tests/test_llm_vllm_qwen.py \
  tests/test_market_agent.py tests/test_market_config.py \
  tests/test_market_historical_scoring.py tests/test_market_postlisting.py \
  tests/test_validate_postlisting_performance.py \
  tests/test_parallel_market_wiring.py tests/test_stock_code.py -q
python scripts/assert_legal_stream_parity.py --self-check
# 全量回归：
python -m pytest tests -q
# 翰思 HTTP E2E（会重启 9100/9101/9102；解析保持 STUB_MODE=True）
# bash tests/e2e_hansiaitai_v34/run_e2e.sh
```

`ipo-risk` 环境已可直接运行 `pytest`。检索侧（表名/跨页）单测在 `retrieval/tests/`：`test_tbl_is_18a_aliases.py`、`test_tbl_bs_18a_aliases.py`、`test_tbl_cf_continuation.py`、`test_company_bs_kind.py`。

### 13.2 关键目录

```
agents/hk_ipo_risk/
├── README.md
├── docs/
│   └── market_sentiment_agent_spec.md   # 市场情绪接入规范（合并用）
├── configs/                 # score_rules / finance_schema / legal_schema / master_rules
│                            # + market_agent / firecrawl / sina_finance（密钥只写 *.local.yaml）
├── scripts/
│   ├── run_finance_legal.py
│   ├── run_market_agent.py / run_market_pilot.py / run_market_postlisting.py
│   ├── batch_finance_legal_18a.py
│   ├── assert_legal_stream_parity.py
│   ├── generate_analysis_report.py      # 专家三份 MD + 总控 IPO 风险预警 MD
│   ├── __init__.py                      # 固定项目内 scripts 包，避免同名三方包抢占
│   └── start_analysis_service.sh
├── service/                 # FastAPI 9102
│   ├── analysis_runner.py   # StreamHub 实时混流；result/meta completed 持久化后再 report_ready
│   ├── report_data.py / report_pdf.py   # ReportData 含走势预判 + 上市后验证
│   ├── thought_mapper.py    # map_* + map_debate_expert_event
│   └── routes_analysis.py   # start/stream/result + agents/status + report/export
├── src/
│   ├── agents/              # finance / legal / market（正式） / master
│   ├── skills/              # toolbox + debate_query/reply + master_detect/debate/embellish/decide/validate/report
│   ├── models/              # debate / evidence / cross_agent / master / market
│   ├── tools/               # schemas / retrieval_tool / llm_client / firecrawl_news / market_data
│   ├── graph/parallel.py / master_graph.py
│   └── llm/prompts.py / master_prompts.py / debate_prompts.py
├── migrations/              # 001_market_evidence.sql
├── tests/
│   └── e2e_hansiaitai_v34/  # 翰思全链路；日志 logs/frontend|backend
├── logs/  reports/  .runtime/debate/  .runtime/analyses/
```

### 13.3 实现索引（按主题）

| 主题 | 文件 |
|------|------|
| 财务工具与托底 / 叙事对齐 | `src/skills/finance_toolbox.py` / `finance_presets.py` |
| 财务抽数与行名归一 | `src/skills/extract_financials.py` / `table_utils.py` / `configs/finance_schema.yaml` |
| 财务规则分 / 跑道不确定 | `src/skills/score_finance.py` / `configs/score_rules.yaml` |
| ReAct 自动收束 | `src/agents/finance_agent.py` / `legal_agent.py` |
| 法务工具与饱和分 | `src/skills/legal_toolbox.py` / `legal_presets.py` / `legal_point_kind.py` |
| 关联交易占比 | `src/skills/extract_legal.py` |
| 辩论素材 | `src/models/debate.py` |
| 总控模型 / 规则 | `src/models/master.py` / `configs/master_rules.yaml` |
| 总控 Agent / 子图 | `src/agents/master_agent.py` / `src/graph/master_graph.py` |
| 总控 Skill | `detect_conflicts` / `run_debate` / `debate_query` / `debate_reply` / `score_embellishment` / `master_decide` / `validate_postlisting_performance` / `generate_warning_report` |
| JSON 截断重试 | `src/skills/llm_json.py`（空 JSON ≠ 不开辩 / ≠ 对照分终裁） |
| 市场正式实现 | `src/agents/market_agent.py` / `src/skills/score_market*.py` / `score_postlisting.py` / `explain_market.py` / `src/tools/firecrawl_news.py` |
| HTTP Thought 映射 | `service/thought_mapper.py`（`map_market_event` + `map_master_event` + `map_debate_expert_event`） |
| HTTP 报告 | `service/report_data.py` / `report_pdf.py`；runner 写专家三份报告和总控 `{代码}_ipo_risk_warning_report.md` |
| 翰思 v3.4 E2E | `tests/e2e_hansiaitai_v34/` |
| 规则配置 | `configs/score_rules.yaml` |
| 财务检索包（Agent 上游） | `retrieval/configs/agent_retrieval_profiles.yaml` / `retrieval/src/retrieval/evidence_expand.py` |
| 市场情绪接入规范 | [`docs/market_sentiment_agent_spec.md`](docs/market_sentiment_agent_spec.md) |

---

## 14. 市场情绪 Agent

部署与验收细节见 [`MARKET_DEPLOY_TEST.md`](MARKET_DEPLOY_TEST.md)。

### 14.1 能力

| 阶段 | 输出 | 说明 |
|------|------|------|
| 上市前 | `risk_score` = 首日破发风险 0–100 | 确定性历史校准分 + LLM ReAct 研判 + 多空辩论 dossier |
| 市场情绪 | `overall_net_support` = -100% 至 +100% | 正数表示支持、负数表示不支持；这是市场情绪主口径，不是 0–100 风险分 |
| 四大模块 | 宏观 / 行业 / IPO 市场 / 舆情 | 舆情先按 `as_of_date` 过滤，再经 LLM 验证相关性；无上市前有效新闻时状态为 unavailable、权重为 0，不按负面或缺失证据计分 |
| 上市后 | D1/D5–D60 检查点 | D1 以及每 5 个交易日；破发锚点为发行价，二级收益以首日开盘价为基准 |

市场分独立写成 `{代码}_market_report.md`；有真实结果时，原始 `market.risk_score` 直接计入 `reference_fundamental_score`，净支持率与整体状态作为不同量纲的上下文供总控研判。总控读取完整 `market` 卡片。总控辩论若点名市场，走 `MarketAgent.respond_to_controller`，使用本地上市前时点数据补证并按 `MARKET_DEBATE_REPLY` 返回结构化回复；市场模块内部的「多空辩论」是市场 Agent 自己的研判，**不是**总控子图里的 `run_debate`。

市场 dossier 的评分主张同时保留 `evidence_ids` 与结构化 `evidence_refs`；这些引用以 `page=null` 表示“非招股书证据”，并携带 `field_code`、字段值、`as_of_date` 与解释。`master_cards.claim_to_card` 会把二者计入 `n_evidence`，因此详细的市场回答不会再因没有招股书页码被误判为无可核验证据。

### 14.2 主要实现文件

- Agent / 模型：`src/agents/market_agent.py`、`src/models/market.py`
- 评分：`src/skills/score_market.py`、`score_market_history.py`、`score_postlisting.py`、`explain_market.py`
- 工具：`src/tools/firecrawl_news.py`、`market_data.py`、`market_debate.py`、`sina_finance_news.py`
- 存储：`src/storage/market_store.py`、`migrations/001_market_evidence.sql`
- 配置：`configs/market_agent.yaml`、`firecrawl.yaml`、`sina_finance.yaml` 及 `*.local.example.yaml`
- CLI：`scripts/run_market_agent.py`、`run_market_pilot.py`、`run_market_postlisting.py`、`fetch_market_news_firecrawl.py`
- 宽表：`market/data/derived/ipo_sentiment_features.csv`、`market/configs/*.yaml`
- 依赖：`requirements-market.txt`（在 `ipo-risk` 环境另装）

密钥只写 `*.local.yaml`（已 gitignore）或环境变量：`IPO_LLM_API_KEY`、`FIRECRAWL_API_KEY`、`MARKET_DATABASE_URL`。仓库内 yaml 的 `api_key` 为空或 `REPLACE_ME`。

### 14.3 主链路接入点

| 文件 | 改动 |
|------|------|
| `src/models/evidence.py` | `AgentResult.agent` 增加 `"market"` |
| `src/config.py` | `resolve_market_agent_settings` / `resolve_firecrawl_settings` / `resolve_sina_finance_settings` |
| `src/graph/parallel.py` | 三专家并行完成后 `merge_results`；市场失败不中断财务/法务 |
| `scripts/run_finance_legal.py` | `--agent market`；`--agent all` 走三路并行；`--stock-code` |
| `service/analysis_runner.py` | HTTP 挂正式市场；`StreamHub` 三路 thought 立刻推 SSE（不缓冲、不回放 jsonl）；start body `ticker`/`stockCode` 优先，否则 parse meta；缺失则 market=`skipped`；先写专家/总控报告文件再 `report_ready` |
| `service/thought_mapper.py` | `map_market_event` + `map_master_event` + `map_debate_expert_event` |
| `configs/market_agent.yaml` | 市场结果为 `{stock_code}_{company}_market.json` / `_market_report.md`；上市后验证为 `{doc_id}_{stock_code}_postlisting.json` / `_postlisting_report.md` |

独立跑市场：

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk
pip install -r requirements-market.txt   # 首次
python scripts/run_market_agent.py --stock-code 02451 --doc-id smoke-02451-offline
```

主链路（财务+法务+市场+总控）：

```bash
python scripts/run_finance_legal.py --agent all --stock-code 03378 ...
```

`--mode`（`run_market_agent.py`）：`auto` / `offline` / `llm`。
