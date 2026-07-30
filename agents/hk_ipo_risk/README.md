# hk_ipo_risk — 港股 IPO 多 Agent（财务 ReAct + 法务预设）

独立于 `agents/ipo`。本轮：**财务 Agent 完整 ReAct（多轮选工具→submit + 规则托底）**；**法务规则抽取/打分**（含 18A 管线 3.5）；**总控/跨 Agent 仅接口占位**。

---

## 架构分层

| 层级 | 含义 | 本轮财务 | 本轮法务 |
|------|------|----------|----------|
| Tool | 原子能力，JSON schema 可调用 | `retrieve_finance` / `extract_metrics` / `derive_gates` / `calc_cash_runway` / `retrieve_context_evidence` | 章节化检索/grep |
| Skill | 可注册业务能力包 | `submit_finance_report`（终局，内含规则托底） | 5 个 stub：governance / shareholder_rights / related_party / contracts_and_ip / regulatory_litigation |
| Agent | LLM 决定调谁、何时结束 | **ReAct 循环**（默认） | 仍规则流水线；下一阶段接 ReAct |

```
FinanceAgent (ReAct)
  think → tool_calls → observe → … → submit_finance_report
       → score_finance 规则托底合并 → scoring_mode=react+rules_floor
  每轮 → logs/（react_turn + tool observation + model_think）

LegalAgent (规则，本轮)
  retrieve → extract_legal(3.1/3.2/3.3，18A 时 +3.5 管线) → score_legal
  Skill 预设见 src/skills/legal_presets.py + configs/legal_schema.yaml
```

分析维度（盈利/现金流/偿债/商业模式）留在 **prompt**，不拆六个可选 Skill。

### 财务评分：`react+rules_floor`（默认）

LLM **已启用**：负责选工具、四维叙述、初始 `risk_score` / `score_breakdown`。  
`submit_finance_report` 时再与 `configs/score_rules.yaml` 的规则分合并，**不是**关掉 LLM。

| 规则码 | 条件 | delta |
|--------|------|------:|
| `CONTINUOUS_LOSS` / `SINGLE_YEAR_LOSS` | 连续亏损 / 最近完整年度亏损（去重） | 25 / 15 |
| `CFO_NEGATIVE` | CFO 持续为负 | 15 |
| `GP_MARGIN_DROP` | 毛利率降幅 >5pp | 10 |
| `CASH_RUNWAY_LT_12` / `CASH_RUNWAY_12_24` | 未盈利且跑道 <12 或 12–24 月 | 20 / 10 |
| `BURN_YOY_UP_30` | 未盈利且消耗同比升 >30% | 15 |

硬信号（未盈利 / 连续亏损 / CFO 持续为负）时，最终分以合并后的 breakdown 为准，防止模型交假低分；并可校正 summary 中与最终等级不符的「低风险」措辞。  
结果里看 `features.scoring_mode`、`features.rules_floor`（含 `llm_score` / `final_score`）。

对比开关：

- 默认 ReAct + 托底 → `react+rules_floor`
- `--finance-pipeline` → 单次 LLM（无多轮工具）
- `--finance-rules-only` → **纯规则**，不调用 LLM

### 发行人类型与抽数要点

| `--issuer-type` | 门控 |
|-----------------|------|
| `general` | 跳过 2.4 / 3.5；盈利则跳过 3.4 |
| `18a` / `18c` / `biotech` | 启用 2.4、3.5；未盈利算现金跑道 |

抽数相关（`extract_financials` / `table_utils`）：

- 主表 text/html 一视同仁；`TBL_IS`/`TBL_BS`/`TBL_CF` 支持明文报表。
- `TBL_BS_COMPANY`（贵公司财务状况表）单独登记证据，**不并入**综合 BS 指标。
- 年份列区分完整年度与中期（`2024_i1` / `2025_i1`）；盈利门控只用完整年度；跑道用最新一期现金，中期 CFO 按 8 个月年化。
- 18A 无产品收入时 `REV` 可缺失，保留 `OTHER_INCOME`，勿把「其他收入」当营收。

---

## 财务工具列表

1. `retrieve_finance` — 财务报表证据  
2. `extract_metrics` — 抽 REV/GP/CFO…  
3. `derive_gates` — 盈利/3.4 门控  
4. `calc_cash_runway` — 未盈利跑道  
5. `retrieve_context_evidence` — 先定位业务/风险因素/概要等章节，再召回带页码的段落/表格证据  
6. `submit_finance_report` — **唯一结束动作**（可解释评分 JSON）

`temperature=0`；system 要求中文 think + JSON。建议模型：`google/gemma-4-31b-it`，避免使用
`:free` 版本做稳定验收（OpenRouter 的 free upstream 容易 429）。

### Token 节流与联调状态

已完成 token 节流：

- ReAct / pipeline LLM 预算：`max_tokens=2048`，`reasoning_max_tokens=256`。
- `extract_metrics` observation 只返回关键指标摘要；完整 metrics 仍保存在 state / 结果 JSON。
- `retrieve_context_evidence` 返回给模型的是短摘录；完整章节证据仍写入 `evidence_summary.section_evidence_hits`。
- tool schema 与 ReAct prompt 已压缩，减少重复说明。
- 低风险快速路径：`derive_gates` 在“已盈利 + CFO 为正 + 毛利率稳定”时返回 `fast_path.eligible=true`。
- LLM 可见摘要中使用 `NET_PROFIT_OR_LOSS`，避免模型把 `NET_LOSS` 字段名误解为亏损。

最新蜜雪财务 ReAct 联调：

- 输出：`.runtime/mixue_finance_react_token_slim_v2.json`
- 报告：`reports/mixue_finance_react_token_slim_v2_report.md`
- 日志：`logs/蜜雪集團_finance_20260724_112441.log`
- 结果：5 轮 ReAct 跑通，`risk_score=0.0`，`risk_level=very_low`
- token：`total_tokens=12737`，较旧 ReAct 的 `15053` 降低约 `15.4%`

### 章节化检索

`retrieval/src/retrieval/section_map.py` 从 `full_parse.json` 的目录、header、title 构建
`SectionMap`，并将 `section_id/page_role/element_category` 写入每个 chunk。新索引中
`section_filter` 会真实过滤章节；旧索引因缺少 `section_map_version` 会在下一次
`build_from_parse` 时重建。

- 非主表上下文：按 intent 定位 `business/risk_factors/summary/...`，不使用 `appendix_only`。
- 财务主表：优先以 `appendix_one` 页区间为硬门控；章节树缺失时才回退 `PageRoleMap/appendix_only`。
- `TBL_IS` 将“合併损益表”和紧随其后的“合併综合收益表”合并为同一跨页证据包。
- `TBL_BS_COMPANY`：贵公司 BS，与综合 `TBL_BS` 分流（见 retrieval `agent_retrieval_profiles.yaml`）。
- 法务规则链复用同一底层函数，分别召回 redemption / related_party / concentration / **pipeline（3.5）**。

章节映射与原始 JSON 的质量对比：

```bash
cd /nfs/users/wuqianqian/IPOI/retrieval
python scripts/analyze_section_map.py \
  --parse ../pdf_parsing/output/samples_batch/xiaomi/full_parse.json \
  --doc-name 小米集团 \
  --out-dir .runtime/section_maps
```

---

## 法务 5 Skill 预设（GPT 七维合并）

| Skill | GPT 来源 | 关注点 |
|-------|----------|--------|
| `legal_governance` | Skill1 | 控股/实控人/一致行动/AB股/董事 |
| `legal_shareholder_rights` | Skill2 | 对赌赎回 + 上市前权利清理 |
| `legal_related_party` | Skill3 | 关联交易公允/依赖 |
| `legal_contracts_and_ip` | Skill4+7 | 重大合同 + IP |
| `legal_regulatory_litigation` | Skill5+6 | 监管处罚 + 诉讼仲裁 |

Prompt：`src/llm/prompts.py`（`LEGAL_*`）。法务**不输出笼统总分**（留给总控）；现有 `score_legal` 暂作参考分。

规则路径已覆盖：`3.1` 对赌赎回、`3.2` 关联交易、`3.3` 集中度；`issuer-type` 为 `18a`/`18c`/`biotech` 时启用 **`3.5` 管线**（`PIPELINE_RISK` → `PIPELINE_DISCLOSURE` / `PIPELINE_HIGH`）。`3.4` 现金消耗归财务 Agent。

---

## 跨 Agent / 总控（占位）

模型：`src/models/cross_agent.py`。并行出口含 `cross_agent_features: []`、`master: null`。

| 主题 | 财务 | 法务 | 总控（未来） |
|------|------|------|--------------|
| 加盟 | 收入依赖 | 合同责任 | 商业模式风险 |
| 供应链 | 成本/集中 | 供应协议 | 供应链风险 |
| 海外 | 汇率/收入 | 境外监管 | 出海合规 |
| 数据 | 相关收入 | 隐私合规 | 数据业务风险 |

---

## 端到端运行

以下以 `pdf_parsing/pdf/qiniu.pdf` 为例：

```text
PDF → full_parse.json → 章节质量报告 → 向量索引 → 财务/法务检索包 → Agent 分析 → Markdown 报告
```

> **HTTP 自动 prep（推荐）**：解析完成后专家服务（9100）自动调用检索前置（**9101** `/internal/retrieval/prepare`）。前端按 [`dataset/interface_new.md`](../../dataset/interface_new.md) 轮询 `GET /api/v1/projects/:clientProjectId/index-status`，仅 `status=ready` 后调用 `analysis/start`。设计见 [`retrieval/docs/retrieval_api_design.md`](../../retrieval/docs/retrieval_api_design.md)。`force` / `agents` / `topK` 在检索服务后端固化。下列 CLI 仍可用于本地调试。

### 1. PDF 多卡多进程解析

先 dry-run 检查 GPU 分配：

```bash
conda activate infinity_parser
cd /nfs/users/wuqianqian/IPOI/pdf_parsing

python batch_parse_samples.py \
  --pdf /nfs/users/wuqianqian/IPOI/pdf_parsing/pdf/qiniu.pdf \
  --output-dir /nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch \
  --gpus auto \
  --page-workers 2 \
  --batch-size 8 \
  --rotate-mode auto \
  --dry-run
```

正式解析：

```bash
conda activate infinity_parser
cd /nfs/users/wuqianqian/IPOI/pdf_parsing

python batch_parse_samples.py \
  --pdf /nfs/users/wuqianqian/IPOI/pdf_parsing/pdf/qiniu.pdf \
  --output-dir /nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch \
  --gpus auto \
  --page-workers 2 \
  --batch-size 2 \
  --max-new-tokens 16384 \
  --rotate-mode none

# 或者
python batch_parse_samples.py   --pdf pdf/03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf   --output-dir /nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch   --gpus auto   --page-workers 2   --batch-size 2   --max-new-tokens 16384   --rotate-mode none
```

输出主文件：

```text
/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/qiniu/full_parse.json
```

如果 OOM，优先把 `--batch-size 8` 降到 `4`；仍 OOM 再把 `--page-workers 2` 降到 `1`。

### 2. 章节映射质量报告

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/retrieval

python scripts/analyze_section_map.py \
  --parse /nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/qiniu/full_parse.json \
  --doc-name 七牛智能 \
  --out-dir /nfs/users/wuqianqian/IPOI/retrieval/.runtime/section_maps

# 或者
python scripts/analyze_section_map.py   --parse /nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/03378_15-12-2025_翰思艾泰－Ｂ_全球發售/full_parse.json   --doc-name 翰思艾泰  --out-dir /nfs/users/wuqianqian/IPOI/retrieval/.runtime/section_maps
```

### 3. 构建向量检索索引

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/retrieval

python scripts/build_index_from_parse.py \
  --parse /nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/qiniu/full_parse.json \
  --company-name 七牛云 \
  --stock-code 02567 \
  --listing-date 20241016 \
  --doc-id qiniu \
  --force

# 或者（注意：--parse 必须对应该公司的 full_parse；doc_name 默认取 parse 父目录名）
python scripts/build_index_from_parse.py --parse /nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/03378_15-12-2025_翰思艾泰－Ｂ_全球發售/full_parse.json --company-name 翰思艾泰 --stock-code 03378 --listing-date 20251215 --doc-id hansiaitai  --force
```

### 4. 生成财务/法务检索包

检索包是 Agent 的离线证据候选集，用于把“证据召回”和“LLM/规则分析”解耦。

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/retrieval

python scripts/simulate_agent_retrieval.py \
  --doc-id qiniu \
  --agent finance \
  --issuer-type general \
  --top-k 5 \
  --out /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_qiniu_finance.json

# 或者
python scripts/simulate_agent_retrieval.py --doc-id hansiaitai --agent finance --issuer-type 18a  --top-k 5 --out /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_finance.json
```

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/retrieval

python scripts/simulate_agent_retrieval.py \
  --doc-id qiniu \
  --agent legal \
  --issuer-type general \
  --top-k 5 \
  --out /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_qiniu_legal.json

# 或者
python scripts/simulate_agent_retrieval.py --doc-id hansiaitai --agent legal --issuer-type 18a  --top-k 5 --out /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_legal.json
```

### 5. 财务/法务 Agent 风险分析

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk

python scripts/run_finance_legal.py \
  --agent all \
  --doc-id qiniu \
  --doc-name 七牛云 \
  --pdf-name qiniu.pdf \
  --issuer-type general \
  --parse-json /nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/qiniu/full_parse.json \
  --retrieval-finance-json /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_qiniu_finance.json \
  --retrieval-legal-json /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_qiniu_legal.json \
  --chat-model google/gemma-4-31b-it \
  --max-turns 8 \
  --out /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/.runtime/qiniu_finance_legal.json

# 或者
python scripts/run_finance_legal.py --agent all --doc-id hansiaitai --doc-name 翰思艾泰 --pdf-name 03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf --issuer-type 18a --parse-json /nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/03378_15-12-2025_翰思艾泰－Ｂ_全球發售/full_parse.json --retrieval-finance-json /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_finance.json --retrieval-legal-json /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_legal.json --chat-model google/gemma-4-31b-it --max-turns 8 --out /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/.runtime/hansiaitai_finance_legal.json
```

仅跑财务 ReAct：

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk

python scripts/run_finance_legal.py \
  --agent finance \
  --doc-id qiniu \
  --doc-name 七牛智能 \
  --pdf-name qiniu.pdf \
  --issuer-type general \
  --parse-json /nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/qiniu/full_parse.json \
  --retrieval-finance-json /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_qiniu_finance.json \
  --chat-model google/gemma-4-31b-it \
  --max-turns 8 \
  --out /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/.runtime/qiniu_finance_react.json
```

如需跳过离线检索包、直接实时查索引，可在 `run_finance_legal.py` 中加：

```bash
--use-live-retrieval
```

### 6. 生成 Markdown 报告

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk

python scripts/generate_analysis_report.py \
  --result /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/.runtime/qiniu_finance_legal.json \
  --doc-name 七牛智能 \
  --pdf-name qiniu.pdf \
  --out /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/reports/qiniu_finance_legal_report.md

# 或者
python scripts/generate_analysis_report.py \
  --result /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/.runtime/hansiaitai_finance_legal.json \
  --doc-name 翰思艾泰 \
  --pdf-name 03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf \
  --out /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/reports/hansiaitai_finance_legal_report.md
```

### 旧流水线 / 规则兜底

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk

# 旧流水线对照：单次 LLM，不用 ReAct
python scripts/run_finance_legal.py \
  --agent finance \
  --doc-id qiniu \
  --doc-name 七牛云 \
  --pdf-name qiniu.pdf \
  --issuer-type general \
  --parse-json /nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/qiniu/full_parse.json \
  --retrieval-finance-json /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_qiniu_finance.json \
  --finance-pipeline \
  --chat-model google/gemma-4-31b-it \
  --out /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/.runtime/qiniu_finance_pipeline.json

# 规则兜底：不调用 LLM
python scripts/run_finance_legal.py \
  --agent finance \
  --doc-id qiniu \
  --doc-name 七牛云 \
  --pdf-name qiniu.pdf \
  --issuer-type general \
  --parse-json /nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/qiniu/full_parse.json \
  --retrieval-finance-json /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_qiniu_finance.json \
  --finance-rules-only \
  --out /nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/.runtime/qiniu_finance_rules.json
```

### 常用参数

| 参数 | 说明 |
|------|------|
| `--issuer-type` | `general` / `18a` / `18c` / `biotech`（影响 2.4/3.4/3.5 门控） |
| `--finance-pipeline` | 单次 LLM，不用 ReAct |
| `--finance-rules-only` | 纯规则打分（无 LLM；与默认「ReAct+托底」不同） |
| `--max-turns` | ReAct 轮次上限（默认 8） |
| `--use-llm` | **法务** LLM 增强（财务默认已用 LLM） |
| `--log-dir` / `--no-run-log` | 推理日志 |

### 翰思艾泰（18A）联调快照

- 结果：`.runtime/hansiaitai_finance_legal.json`
- 报告：`reports/hansiaitai_finance_legal_report.md`
- 要点：`scoring_mode=react+rules_floor`；主表含 `TBL_BS_COMPANY`；中期列 `*_i1`；法务 `3.5` 有 `PIPELINE_DISCLOSURE`

---

## 推理日志

`logs/{doc}_finance_{ts}.log` + `.jsonl`：时间、文档信息、**react turn**（model_think + planned tools）、工具 observation、结果。

---

## 目录

- `src/tools/schemas.py` — Tool schema + ToolRegistry  
- `src/skills/base.py` / `registry.py` — Skill 基类  
- `src/skills/finance_toolbox.py` — 财务工具 + **规则托底**  
- `src/skills/extract_financials.py` / `table_utils.py` — 主表抽数、中期列  
- `src/skills/extract_legal.py` / `score_legal.py` — 法务 3.1–3.5  
- `src/skills/legal_presets.py` — 法务 Skill 骨架  
- `src/agents/react_loop.py` — ReAct 执行器  
- `src/agents/finance_agent.py` — 默认 ReAct  
- `src/models/cross_agent.py` — 跨 Agent 特征  
- `src/llm/prompts.py` — 财务 ReAct + 法务预设 prompt  
- `configs/score_rules.yaml` / `finance_schema.yaml` / `legal_schema.yaml`  
- `logs/` / `reports/` / `tests/test_year_headers_and_pipeline.py`
