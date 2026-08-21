# 港股 IPO 多 Agent 专家协作体系 — 架构图 / 流程图 / 泳道图

> **用途**：赛题答辩，面向金融领域从业人员  
> **范围**：`agents/hk_ipo_risk` 现行实现（财务 ‖ 法务 ‖ 市场 三专家并行 → 总控 LangGraph 子图）  
> **说明**：中文为主，保留 Agent / Tool / Skill / ReAct / DebateDossier 等英文名词；**正式风险等级以总控终裁为准**，对照加权分 `reference_fundamental_score` 仅作参考

---

## 图 1 · 系统分层架构图

```mermaid
flowchart TB
    subgraph INPUT["📥 输入 Input"]
        I1["招股书 PDF<br/>Prospectus PDF"]
        I2["股票代码 ticker / stockCode<br/>例：03378.HK"]
        I3["发行人类型 issuerType<br/>general / 18a / biotech"]
        I4["LLM 配置 llmConfig<br/>（可选）"]
    end

    subgraph PREP["🔧 数据准备层 Data Preparation"]
        P1["pdf_parsing :9100<br/>Infinity-Parser 解析"]
        P2["full_parse.json<br/>结构化全文 + 表格"]
        P3["retrieval :9101<br/>向量索引 + 检索包"]
        P4["agent_retrieval_{doc}_finance.json<br/>财务整表包 TBL_IS/BS/CF"]
        P5["agent_retrieval_{doc}_legal.json<br/>法务检索包 + grep 基线"]
        P6["market/data<br/>宏观/行业/IPO 历史特征 CSV"]
    end

    subgraph EXPERTS["🧠 三专家并行层 Expert Agents :9102"]
        direction LR
        E1["FinanceAgent<br/>财务穿透 Agent<br/>ReAct + rules_floor"]
        E2["LegalAgent<br/>法务合规 Agent<br/>ReAct + rules_floor"]
        E3["MarketAgent<br/>市场情绪 Agent<br/>历史校准 + LLM ReAct"]
    end

    subgraph MASTER["⚖️ 总控决策层 Master Orchestration"]
        M1["MasterAgent<br/>LangGraph 子图"]
        M2["detect_conflicts<br/>冲突研判"]
        M3["run_debate<br/>条件辩论 ≤3 轮"]
        M4["score_embellishment<br/>前五页粉饰 0–10"]
        M5["master_decide<br/>终裁 0–100"]
        M6["validate_postlisting_performance<br/>D1/D5/D20/D60 上市后验证"]
        M7["generate_warning_report<br/>报告排版"]
    end

    subgraph OUTPUT["📤 输出 Output"]
        O1["AgentResult ×3<br/>risk_score / risk_points / evidence"]
        O2["DebateDossier ×3<br/>claims + evidence_refs + 页码"]
        O3["reference_fundamental_score<br/>对照加权分（参考）"]
        O4["master.judgment<br/>overall_score + riskLevel<br/>★ 正式等级"]
        O5["*_master_*.json + report_markdown"]
        O6["HTTP result.json<br/>phase / debate / report"]
        O7["reports/{ticker}_finance|legal|market_report.md<br/>三份独立专家报告"]
        O8["GET /report JSON + /report/export PDF"]
    end

    I1 --> P1 --> P2
    P2 --> P3
    P3 --> P4 & P5
    I2 --> E3
    I3 --> E1 & E2
    P2 --> E1 & E2
    P4 --> E1
    P5 --> E2
    P6 --> E3

    E1 & E2 & E3 -->|"asyncio.gather<br/>三专家并行完成"| M1
    M1 --> M2
    M2 -->|"need_debate?"| M3
    M2 -->|"无冲突/纯共振"| M4
    M3 --> M4 --> M5 --> M6 --> M7

    E1 --> O1 & O2
    E2 --> O1 & O2
    E3 --> O1 & O2
    M1 --> O3
    M5 --> O4
    M7 --> O5
    M1 --> O6
    M7 --> O8
    E1 & E2 & E3 --> O7

    style O4 fill:#ffe0e0,stroke:#c0392b,stroke-width:2px
    style M5 fill:#ffe0e0,stroke:#c0392b,stroke-width:2px
```

**架构要点**

| 层级 | 核心职责 | 关键产物 |
|------|----------|----------|
| 数据准备 | PDF → 结构化 JSON → 向量索引 + Agent 检索包 | `full_parse.json`、finance/legal 检索包 |
| 三专家 | 各自 ReAct 推理 + 规则托底，产出带页码证据的风险分 | `AgentResult` + `DebateDossier` |
| 总控 | 冲突研判 → 条件辩论 → 粉饰 → **终裁** → 上市后验证 → 报告 | `master.judgment`（正式分）+ `post_listing` |
| 网关 | 前端只连 `:9100`，反代 `analysis/*`、`report*`、`agents/status` 到 `:9102` | SSE 实时混流 + `result` / `report` / PDF |

---

## 图 2 · 端到端业务流程图（从上传到报告）

```mermaid
flowchart TD
    START(["开始<br/>用户上传招股书 + 填写 ticker"])

    START --> A1["POST /parse/expert/start :9100<br/>输入：PDF + ticker + isBiotech"]
    A1 --> A2{"解析 stage = READY?"}
    A2 -->|否，轮询| A2
    A2 -->|是| A3["输出：full_parse.json<br/>+ parse task meta"]

    A3 --> B1["内部调用 retrieval/prepare :9101<br/>建 FAISS/BM25 索引"]
    B1 --> B2{"indexStatus = ready?"}
    B2 -->|否，轮询| B2
    B2 -->|是| B3["输出：finance/legal 检索包<br/>agent_retrieval_{taskId}_*.json"]

    B3 --> C1["POST /analysis/start :9100→9102<br/>输入：taskId + ticker + llmConfig"]
    C1 --> C2["并行启动三专家<br/>run_finance_legal_market_parallel"]

    C2 --> D1["FinanceAgent ReAct"]
    C2 --> D2["LegalAgent ReAct"]
    C2 --> D3["MarketAgent<br/>历史分 + LLM ReAct"]
    D3 -.->|失败| D3E["market_error<br/>不阻断其他 Agent"]
    D3E --> D4

    D1 --> D4["merge_results<br/>对照分 reference_fundamental_score"]
    D2 --> D4
    D3 --> D4

    D4 --> E1["MasterAgent 总控子图"]
    E1 --> E2["① detect_conflicts<br/>输出：conflicts[] + need_debate"]
    E2 --> E3{"need_debate<br/>或 need_discussion?"}
    E3 -->|是| E4["② run_debate ≤3 轮<br/>finance/legal/market 补证答辩"]
    E3 -->|否| E5["③ score_embellishment<br/>前五页文本粉饰 0–10"]
    E4 --> E5
    E5 --> E6["④ master_decide<br/>★ 终裁 overall_score + level"]
    E6 --> E7["⑤ validate_postlisting_performance<br/>对齐 D1/D5/D20/D60 预测与真实行情"]
    E7 --> E8["⑥ generate_warning_report<br/>ReportData + 总控摘要"]
    E8 --> E9["⑦ 写三份独立专家 MD<br/>finance / legal / market"]
    E9 --> E10["⑧ 落盘 report/result.json<br/>并置 status=completed"]
    E10 --> E11["⑨ report_ready<br/>开放 /report 与 /report/export"]

    E10 --> F1["落盘产物"]
    F1 --> F2[".runtime/{doc}_finance_legal*.json"]
    F1 --> F3[".runtime/debate/*_dossier_*.json"]
    F1 --> F4[".runtime/debate/*_master_*.json"]
    F1 --> F5["reports/{ticker}_finance|legal|market_report.md"]
    F1 --> F6[".runtime/analyses/{analysisId}/report.json"]

    E11 --> G1["HTTP 输出"]
    G1 --> G2["SSE：thought / agent_status / agent_report<br/>phase_change / debate_* / report_ready"]
    G1 --> G3["result.json<br/>overallScore + riskLevel + phase + debate<br/>★ 总控终裁"]
    G1 --> G4["GET /report<br/>ReportData JSON"]
    G1 --> G5["GET /report/export<br/>PDF"]

    G2 --> END(["结束<br/>前端展示 Agent 协作 + 证据溯源"])
    G3 --> END
    G4 --> END
    G5 --> END
    F5 --> END

    style E6 fill:#ffe0e0,stroke:#c0392b,stroke-width:2px
    style G3 fill:#ffe0e0,stroke:#c0392b,stroke-width:2px
```

**对照分 vs 终裁分**

```
reference_fundamental_score（参考，非正式等级）
  = 基本面 legal×0.55 + finance×0.45
  = 有市场时 (基本面)×0.65 + market×0.35

正式 riskLevel / overallScore ← master_decide 终裁
```

---

## 图 3 · 泳道图（Swimlane）：三专家并行 + 总控编排 + 前端回传

```mermaid
flowchart TB
    subgraph L0["泳道：用户 / 前端 Frontend"]
        U1["上传 PDF + ticker"]
        U2["轮询解析 / 索引状态"]
        U3["订阅 SSE stream"]
        U4["查看 result + 证据高亮"]
        U5["拉取 /report JSON 与 PDF"]
    end

    subgraph L1["泳道：网关 Gateway :9100"]
        G1["解析路由 parse/*"]
        G2["反代 analysis/* → :9102"]
        G3["反代 /agents/status /report /report/export → :9102"]
    end

    subgraph L2["泳道：数据服务 Data Services"]
        S1["pdf_parsing 解析"]
        S2["retrieval 索引 + 检索包"]
    end

    subgraph L3["泳道：财务 Agent FinanceAgent"]
        F_IN["输入：finance 检索包 + full_parse"]
        F1["retrieve_finance"]
        F2["extract_metrics → derive_gates"]
        F3["run_finance_skill ×4"]
        F4["run_finance_rule_checks"]
        F5["submit_finance_report"]
        F_OUT["输出：AgentResult + DebateDossier<br/>risk_score / 规则码 / 页码证据"]
    end

    subgraph L4["泳道：法务 Agent LegalAgent"]
        L_IN["输入：legal 检索包 + full_parse"]
        L1["retrieve_legal"]
        L2["run_legal_skill ×5"]
        L3["run_rule_checks"]
        L4["submit_legal_report"]
        L_OUT["输出：AgentResult + DebateDossier<br/>risk_points + point_kind"]
    end

    subgraph L5["泳道：市场 Agent MarketAgent"]
        M_IN["输入：stockCode + 历史特征 CSV"]
        M1["HistoricalMarketRiskScorer<br/>确定性校准分"]
        M2["LLM ReAct 四大模块<br/>宏观/行业/IPO/舆情"]
        M3["Market 内部多空辩论"]
        M4["submit_market_report"]
        M_OUT["输出：AgentResult + DebateDossier<br/>day1_break_risk / D5–D60"]
        M_ERR["market_error（可选）<br/>失败不阻断"]
    end

    subgraph L6["泳道：总控 Agent MasterAgent / Orchestrator"]
        O_IN["输入：三路 AgentResult + 短卡片"]
        O1["dossier_to_cards 压卡片"]
        O2["detect_conflicts<br/>conflict / resonance / evidence_gap"]
        O3["run_debate<br/>≤3轮 × ≤4问/轮<br/>search_*_standalone 补证"]
        O4["score_embellishment"]
        O5["master_decide ★终裁"]
        O6["validate_postlisting_performance<br/>D1/D5/D20/D60 验证"]
        O7["generate_warning_report<br/>ReportData"]
        O8["写三份独立 MD + report/result<br/>置 completed 后再发 report_ready"]
        O_OUT["输出：judgment + master dossier<br/>riskLevel HIGH|MEDIUM|LOW"]
    end

    U1 --> G1 --> S1
    S1 --> S2
    U2 --> G1
    S2 --> F_IN & L_IN
    U1 --> M_IN

    F_IN --> F1 --> F2 --> F3 --> F4 --> F5 --> F_OUT
    L_IN --> L1 --> L2 --> L3 --> L4 --> L_OUT
    M_IN --> M1 --> M2 --> M3 --> M4 --> M_OUT
    M2 -.-> M_ERR

    F_OUT & L_OUT & M_OUT --> O_IN
    O_IN --> O1 --> O2
    O2 -->|"need_debate / need_discussion"| O3 --> O4
    O2 -->|"跳过辩论"| O4
    O4 --> O5 --> O6 --> O7 --> O8 --> O_OUT

    O_OUT --> G2
    F_OUT & L_OUT & M_OUT --> G2
    O_OUT --> G3
    G2 --> U3 & U4
    G3 --> U5

    style O5 fill:#ffe0e0,stroke:#c0392b,stroke-width:2px
    style O_OUT fill:#ffe0e0,stroke:#c0392b,stroke-width:2px
```

**并行时序说明**

```
时间轴 ──────────────────────────────────────────────────────────►

FinanceAgent  ████████████████████ submit_finance_report
LegalAgent    ████████████████████████ submit_legal_report
MarketAgent   ██████████████ submit（或 market_error）
              └──────── asyncio.gather ────────┘
                                              │
                                              ▼
MasterAgent                              detect → debate? → embellish → decide → validate → report
Runner/UI                                写 MD/report/result → status=completed → report_ready → /report JSON/PDF
```

---

## 图 4 · 总控 LangGraph 子图（Master Subgraph）

> 专家探查（Finance / Legal / Market ReAct）**不在**此子图内；三专家完成后才进入。

```mermaid
stateDiagram-v2
    [*] --> detect: 输入三路短卡片\n+ reference_fundamental_score\n+ 第五章风险清单

    detect --> debate: need_debate=true\n或 任一条 need_discussion=true
    detect --> embellish: 无冲突 / 纯 resonance\n且 need_debate=false

    debate --> embellish: 最多 3 轮\n每轮 ≤4 问并行\n补证 search_*_standalone

    embellish --> decide: 前五页粉饰分 0–10\nlow / medium / high

    decide --> validate_postlisting: overall_score 0–100\n+ level + risk_factors\n★ 正式终裁

    validate_postlisting --> report: 对齐 D1/D5/D20/D60\n计算 weighted_hit_score\n无数据则 not_available

    report --> [*]: 输出 master dossier\n+ result.report / report.json

    note right of detect
        conflicts[].kind:
        • conflict → 应开辩
        • resonance → 同向印证，非打架
        • evidence_gap → 可补证开辩
    end note

    note right of decide
        闸门 gate_warning:
        终裁 low 但含
        CASH_RUNWAY_LT_12 /
        REDEMPTION_HIGH 等
        → LLM 修订一次
    end note
```

---

## 图 5 · 单专家 ReAct 内部流程（Tool / Skill 编排）

### 5.1 财务 Agent FinanceAgent

```mermaid
flowchart LR
    subgraph FIN_IN["输入"]
        FI1["finance 检索包"]
        FI2["full_parse.json"]
        FI3["issuerType 门控"]
    end

    subgraph FIN_REACT["ReAct 循环 max_turns=10"]
        FT1["retrieve_finance<br/>消费整表包"]
        FT2["extract_metrics<br/>REV/CFO/NET_LOSS…"]
        FT3["derive_gates<br/>盈利/3.4/biotech"]
        FT4["calc_cash_runway<br/>未盈利跑道"]
        FT5["run_finance_skill ×4<br/>profitability/cash_flow<br/>solvency/business_context"]
        FT6["search_finance_evidence<br/>配额 ≤2/3"]
        FT7["run_finance_rule_checks<br/>react+rules_floor"]
        FT8["submit_finance_report<br/>★ 唯一结束动作"]
    end

    subgraph FIN_OUT["输出"]
        FO1["risk_score 0–100"]
        FO2["score_breakdown<br/>CONTINUOUS_LOSS 等规则码"]
        FO3["evidence_refs 页码+片段"]
        FO4["DebateDossier 落盘"]
    end

    FI1 & FI2 & FI3 --> FT1 --> FT2 --> FT3 --> FT4 --> FT5 --> FT6 --> FT7 --> FT8
    FT8 --> FO1 & FO2 & FO3 & FO4
```

### 5.2 法务 Agent LegalAgent

```mermaid
flowchart LR
    subgraph LEG_IN["输入"]
        LI1["legal 检索包"]
        LI2["full_parse.json"]
        LI3["issuerType + gates"]
    end

    subgraph LEG_REACT["ReAct 循环 max_turns=10"]
        LT1["retrieve_legal"]
        LT2["run_legal_skill ×5<br/>governance/shareholder_rights<br/>related_party/contracts_and_ip<br/>regulatory_litigation"]
        LT3["search_legal_evidence<br/>配额 ≤2/3"]
        LT4["run_rule_checks<br/>饱和聚合 + point_kind"]
        LT5["submit_legal_report<br/>★ 唯一结束动作"]
    end

    subgraph LEG_OUT["输出"]
        LO1["risk_score 0–100"]
        LO2["risk_points[]<br/>issuer_specific / structural"]
        LO3["3.2 关联交易占比 ratio_pct"]
        LO4["DebateDossier 落盘"]
    end

    LI1 & LI2 & LI3 --> LT1 --> LT2 --> LT3 --> LT4 --> LT5
    LT5 --> LO1 & LO2 & LO3 & LO4
```

### 5.3 市场 Agent MarketAgent

```mermaid
flowchart LR
    subgraph MKT_IN["输入"]
        MI1["stockCode"]
        MI2["ipo_sentiment_features.csv"]
        MI3["Firecrawl / 新浪舆情（可选）"]
    end

    subgraph MKT_PIPE["Pipeline"]
        MT1["HistoricalMarketRiskScorer<br/>★ 确定性权威分"]
        MT2["LLM ReAct 四大模块<br/>宏观/行业/IPO市场/舆情"]
        MT3["Market 内部多空辩论<br/>（非总控 run_debate）"]
        MT4["submit_market_report"]
    end

    subgraph MKT_OUT["输出"]
        MO1["risk_score + day1_break_risk"]
        MO2["deterministic_score + llm_score"]
        MO3["上市后 D1/D5–D60 检查点"]
        MO4["DebateDossier 落盘"]
    end

    MI1 & MI2 & MI3 --> MT1 --> MT2 --> MT3 --> MT4
    MT4 --> MO1 & MO2 & MO3 & MO4
```

---

## 图 6 · 跨 Agent 职责分轨（避免重复计分）

```mermaid
flowchart LR
    subgraph THEME["风险主题 Theme"]
        T1["赎回/优先股<br/>Redemption / CV Pref"]
        T2["现金跑道<br/>Cash Runway"]
        T3["客户/供应商集中<br/>Concentration"]
        T4["关联交易占比<br/>Related Party"]
        T5["首日破发/板块<br/>Day-1 Break Risk"]
        T6["文本粉饰<br/>Embellishment"]
    end

    subgraph FIN["FinanceAgent"]
        F_T1["CV_PREF_LIABILITY 表内负债"]
        F_T2["CASH_RUNWAY_* / BURN_YOY_*"]
    end

    subgraph LEG["LegalAgent"]
        L_T1["REDEMPTION_* 条款/清理"]
        L_T3["CONCENTRATION_*"]
        L_T4["RELATED_PARTY_* + ratio_pct"]
    end

    subgraph MKT["MarketAgent"]
        M_T5["day1_break_risk 等"]
    end

    subgraph MST["MasterAgent"]
        MS_T1["同向 → resonance 共振<br/>表内 vs 已清理 → conflict"]
        MS_T6["score_embellishment 独占"]
    end

    T1 --> F_T1 & L_T1 --> MS_T1
    T2 --> F_T2
    T3 --> L_T3
    T4 --> L_T4
    T5 --> M_T5
    T6 --> MS_T6
```

---

## 图 7 · 输入 / 输出契约总表（答辩速查）

| 阶段 | 输入 Input | 处理 Process | 输出 Output |
|------|------------|--------------|-------------|
| **解析** | PDF、companyName、ticker | Infinity-Parser OCR+表格 | `full_parse.json`、taskId |
| **检索** | full_parse、doc_id、issuerType | FAISS/BM25 + 整表展开 | finance/legal 检索包 |
| **财务** | finance 检索包、parse JSON | ReAct + 4 Skills + rules_floor | `AgentResult` + `DebateDossier` |
| **法务** | legal 检索包、parse JSON | ReAct + 5 Skills + 饱和聚合 | `AgentResult` + `DebateDossier` |
| **市场** | stockCode、特征 CSV、舆情 | 历史校准 + LLM ReAct | `AgentResult` + `DebateDossier` |
| **合并** | 三路 AgentResult | `reference_fundamental` 对照分 | merged JSON |
| **总控** | 短卡片 + 第五章清单 | detect → debate? → embellish → decide → validate_postlisting | `master.judgment` ★ + `post_listing` |
| **报告** | 终裁 JSON + dossier + 上市后验证 | ReportData 汇总 + 三份独立专家 MD | `*_finance_report.md`、`*_legal_report.md`、`*_market_report.md`、`report.json` |
| **前端** | analysisId | SSE 实时混流 + `report_ready` 后拉取报告 | `result.json`、`GET /report`、`GET /report/export`、overallScore + riskLevel ★ |

---

## 前端契约更新要点

1. **前端唯一 Base 仍是 `:9100`**，但除 `analysis/*` 外，现还会经网关访问 `GET /api/v1/agents/status`、`GET .../report`、`GET .../report/export`。
2. **SSE 不再按 legal → financial → market 顺序缓冲回放**，而是三专家与总控 **实时混流**；谁先产生事件谁先推送。
3. **`category` 只在真实辩论阶段出现**。初评、冲突研判、粉饰、终裁、skip-debate 都没有 `category`。
4. **`report_ready` 在三份独立专家 MD、`report.json`、完整 `result.json` 均落盘且任务已置为 `completed` 后才发送**；收到事件后前端可立即拉取 `/report` 和 `/report/export`，不会命中 `REPORT_NOT_READY` 的时序窗口。
5. **综合章与专家章分离**：总控 `generate_warning_report` 负责 `result.report` / `/report` 的综合输出；财务、法务、市场则分别写成三份独立 Markdown。

---

## 渲染说明

- **GitHub / GitLab / Typora / Obsidian**：直接预览 Mermaid 代码块
- **答辩 PPT**：推荐 [Mermaid Live Editor](https://mermaid.live) 导出 SVG/PNG
- **图 3 泳道图**较宽，导出时建议横向 16:9 画布
- 红色高亮节点 = **正式终裁输出**，答辩时重点强调「不是简单加权平均，而是证据驱动的总控决策」

---

*文档版本：2026-08-20 · 对齐 `agents/hk_ipo_risk` 当前实现*
