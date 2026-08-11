# 翰思艾泰 — 财务/法务 Agent 结果分析报告

- 生成时间：2026-08-05 00:42:22（DeepSeek 联合跑分 + 事后解读）
- 招股书：`03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf`（03378，18A）
- doc_id：`hansiaitai`
- 结果 JSON：`.runtime/hansiaitai_finance_legal.json`
- 参考基本面融合分：`57.45`（legal×0.45 + finance×0.55；总控未启用）
- 财务/法务评分模式：均为 `react+rules_floor`
- 推理日志：
  - 财务：`logs/翰思艾泰_finance_20260805_003602.log`
  - 法务：`logs/翰思艾泰_legal_20260805_003602.log`
- 辩论素材：`.runtime/debate/hansiaitai_legal_dossier_20260805_003736.json`

---

## 0. 联合分析结论（解读）

### 0.1 一句话结论

财务侧为典型 **18A 未盈利 + 连续亏损 + CFO 为负、跑道约 20 个月**，参考分 **50 / medium**，归因清晰、过程完整。  
法务侧完成 5 个 Skill、汇总约 19–22 个风险点，参考分 **66.5 / high**；相对「结构关注、无重大诉讼、保发预期」的经验中位（约 40–60），**偏高约一档**，主因是赎回/权利清理与 IP 驳回被标 high 全额进分，且治理/关连被模型标成 `issuer_specific` 未走 structural 折减；另 **8 轮未主动 submit，依赖 auto-submit**。

融合参考分 **57.45** ≈ 财务中位与法务偏高的加权，总控辩论仍为空。

### 0.2 分数对照

| 口径 | 分数 | 等级 | 说明 |
|------|-----:|------|------|
| 财务 ReAct+规则托底 | 50.0 | medium | = 规则实质分（LLM 初始分 0，全靠托底） |
| 法务 ReAct+分型饱和 | 66.55 | high | 饱和聚合；`rules_score=51`，实质规则托底仅 12 |
| 融合 `0.55×财+0.45×法` | 57.45 | （参考） | 非总控裁决 |
| 计分校准离线重放（旧 points，IP=medium） | ~59 | medium | 见 README；本跑 IP 升为 high(+18) 是抬分关键差 |

### 0.3 财务侧读法

| 信号 | 证据要点 | 贡献 |
|------|----------|-----:|
| 连续亏损 | NET_LOSS：2023=-85.2m、2024=-116.9m（人民币千元） | +25 |
| CFO 持续为负 | 2023/2024 及中期均为负 | +15 |
| 现金跑道 12–24 月 | runway≈**20.2** 月（END_CASH 150m / 月烧约 7.4m） | +10 |
| 优先股负债 | CV_PREF≈138.5m（与法务赎回金额同量级） | 未单独加分，与法务赎回主题交叉 |

过程质量：**6 轮正常 submit**，主表定位完整（IS/BS/CF/BS_COMPANY）。弱点：`retrieve_context_evidence` 对业务/商业模式 **0 hit**（章节检索缺口），四维叙述偏弱，但不影响规则托底分。

对 18A 生物科技：中位财务风险合理——烧钱与未盈利是行业常态，跑道未跌破 12 个月，故未到 high。

### 0.4 法务侧读法

**进分主题（饱和后合计 66.5）**

| 主题/代码 | delta | 性质 | 点评 |
|-----------|------:|------|------|
| 权利清理未完成 | 20 | 发行人特异 | 上市失败则特别权利恢复——真实结构风险，权重合理偏高 |
| 赎回期限&金额 | 18 | 发行人特异 | 覆盖规则 `REDEMPTION_MEDIUM(12)`；金额与 BS 的 CV_PREF 一致 |
| FcRn 专利驳回 | 18 | 发行人特异、**level=high** | 有「驳回」事实，但法律顾问认为未必无效；标 high 使 IP 桶与赎回同级，是相对校准样本抬分主因之一 |
| 社保公积金补缴 | 15 | 被标 issuer_specific | 叙述含「风险相对较小 / 已承诺补缴」，实质偏常规合规瑕疵，15 分偏重 |
| 控股>50% | 10 | 模型标 `issuer_specific` | 计划默认应 ×0.6→6；因带 55.89% 被当成特异事实保留全额 |
| 关连协议超三年 | 8 | 同上，未 structural 折减 | 预期约 4.8 |
| 集中度/管线披露 | 6+6 | 空主题披露×0.5 | 披露隔离生效，但仍有基线贡献 |

**未进分但仍留在列表（正确行为）**：约 7 条 boilerplate（FDA 套话、专利维护套话等）、`LITIGATION_ABSENT` 类阴性、部分 disclosure_only。风险点展示与参考分已分离。

**过程问题**

1. `max_turns=8` 耗尽仍未调用 `submit_legal_report` → `auto_submit:max_turns_exceeded_without_submit`  
2. 理想路径需 retrieve+5 skill+rule_checks+submit；本跑 skill 已齐，但收束靠系统，过程可追踪性在末轮打折  
3. 耗时约 **94s**（财务约 55s）；并行总墙钟约 1.5 分钟量级

### 0.5 财务×法务交叉

- **赎回/优先股**：财务 `CV_PREF≈138.5m` ↔ 法务 `REDEMPTION_HIGH` 同金额——交叉一致，可信度高。  
- **流动性叙事**：财务跑道 20 月 vs 法务「赎回触发不足 12 个月」——若未能上市触发赎回，短债压力会突然显性化，这是联合解读的关键张力，而非矛盾。  
- **无重大诉讼**：法务阴性点支持「非事件驱动高风险」；抬分主要来自条款结构 + IP 程序结果，而非诉讼败诉。  
- 总控/跨 Agent：`master=null`，`cross_agent_features=[]`，尚未做加盟/供应链等主题辩论。

### 0.6 与「保发 / medium」预期的差距

校准目标曾希望翰思类样本法务落在 **40–60 medium**。本跑 **66.5 high**，差距来源（按影响大致排序）：

1. `IP_PATENT_REJECTION_RISK` 标 **high→+18**（旧重放多为 medium→+8）  
2. `GOVERNANCE_*` / `RELATED_PARTY_TERM` 被模型标 `issuer_specific` 且文本含比例/日期 → 分类器未收紧为 structural  
3. `REGULATORY_PENALTY`（社保公积金）全额 15  
4. Auto-submit 未改变合并公式，但暴露 ReAct 收束不稳  

若仅将治理/关连按 structural 折减、IP 维持 medium，参考分会更接近 medium 带（与离线 ~59 同量级）。**不建议**用上市涨跌幅事后改分；应继续收紧 `point_kind` / level 校准。

### 0.7 建议后续动作

1. 分类器：对 `GOVERNANCE_CONTROL_GT_50` **强制 structural**（忽略模型 issuer_specific），与计划「默认至少 structural」完全对齐  
2. Skill prompt：社保公积金「已承诺补缴且影响有限」→ `structural` 或 medium/low，避免 `REGULATORY_PENALTY` 高码  
3. IP 驳回：有顾问「未必无效」时默认 medium，除非有产品商业化直接受阻证据  
4. ReAct：rule_checks 后强制下一轮只能 submit；或 auto-submit 前提前 1 轮注入 submit nudge（已有部分逻辑，本跑仍未吃到）  
5. 补市场验证：用行情表核对 03378 首日/5日是否破发，作预警效力反验（本环境未挂载 `hksharedescription` 数据文件，报告未写死涨跌幅）

---

## 1. 总览

| Agent | 风险分 (0-100↑风险) | 等级 | 摘要 |
|-------|---------------------|------|------|
| 财务穿透 | **50.0** | medium | ReAct 财务风险分 50.0 (medium)；6 轮正常 submit |
| 法务合规 | **66.55** | high | 自动收束（max_turns 未 submit）；5 skill / ~22 风险点 |

## 2. 财务穿透 Agent

### 2.1 得分与分解

| 代码 | 加分 | 规则 | 指标值 | 说明 | 证据页 |
|------|------|------|--------|------|--------|
| CONTINUOUS_LOSS | +25.0 | doc§2.1 | — | （规则托底） | 562 |
| CFO_NEGATIVE | +15.0 | doc§2.3 | — | （规则托底） | 569 |
| CASH_RUNWAY_12_24 | +10.0 | doc§3.4 | — | （规则托底） | 563 |

### 2.2 四维分析（LLM）

_无四维分析输出（可能为规则兜底路径）_

### 2.3 推理链

**[model_think 摘录]**（全文见 logs）

> Context evidence retrieval returned 0 hits for business_context and business_model. So business_context dimension has weak/no evidence. Per constraint 6: business_context 无强证据则标 skipped/证据较弱.  Let me also consider checking franchise/supply chain? Not needed for an 18A biotech. The evidence retrieval returned no hits, so I'll mark business_context as 证据较弱/skipped.  Now let me compose the final report.  Financial data summary (人民币千元): - Revenue: none (18A, no product revenue). OTHER_INCOME 6,664 (

### 2.4 门控

```json
{
  "is_unprofitable": true,
  "latest_full_year_loss": true,
  "continuous_net_loss": true,
  "profitability_known": true,
  "profitability_status": "unprofitable",
  "profitability_basis": "NET_LOSS/年內利潤 series; positive=profit",
  "issuer_type": "18a",
  "is_biotech_18a": true,
  "skip_3_4": false,
  "skip_3_4_reason": null,
  "skip_2_4": false,
  "skip_2_4_reason": null,
  "skip_3_5": false,
  "skip_3_5_reason": null
}
```

### 2.5 抽取指标

| 指标 | 2023 | 2024 | 2024_i1 | 2025_i1 |
|------|------|------|------|------|
| OTHER_INCOME | 6,664 | 7,681 | 12,313 | 2,626 |
| RD_EXP | -46,663 | -74,721 | -50,523 | -56,178 |
| SGA | -17,220 | -46,192 | -16,116 | -27,436 |
| NET_LOSS | -85,160 | -116,922 | -48,420 | -87,438 |
| NET_ASSETS | 319,581 | 216,604 | — | 144,791 |
| CASH_EQ | 162,000 | 161,214 | — | 150,000 |
| CV_PREF | — | 131,564 | — | 138,481 |
| TOTAL_ASSETS | 586,240 | 501,471 | — | 444,298 |
| TOTAL_LIAB | 266,659 | 284,867 | — | 299,507 |
| CFO | -51,994 | -104,894 | -67,918 | -59,390 |
| CFI | 93,956 | 96,620 | 78,432 | 35,742 |
| CFF | 90,220 | 6,486 | 8,463 | 12,492 |
| END_CASH | 162,000 | 161,214 | 181,346 | 150,000 |

3.4 现金消耗：skipped=`False`，reason=`None`，runway=`20.21`

### 2.6 召回证据（主表）

| 表/字段 | 页码 | 类型 | 命中数 | 年份列 | 摘录 |
|--------|------|------|--------|--------|------|
| TBL_IS | 562 | text | — | — | 截至12月31日止年度 截至8月31日止八個月 附註 2023年 2024年 2024年 2025年 人民幣千元 人民幣千元 人民幣千元 人民幣千元 其他收入及收益 5 6,664 7,681 12,313 2,626 研發成本 5 (46,663) (74,721) (50,523) (56,178) 行政開支 6 (17,220) (46,192) (16,116) (27,436) 其他開… |
| TBL_BS | 563 | text | — | — | 附註 於12月31日 於8月31日 2023年 2024年 2025年 人民幣千元 人民幣千元 人民幣千元 非流動資產 物業、廠房及設備 14 8,340 11,820 11,907 使用權資產 15 15,661 12,309 10,525 其他無形資產 16 558 447 587 預付款項、其他應收款項及其他資產 18 531 330 330 按公允價值計入損益（「按公允價值計入損益」）的… |
| TBL_CF | 569 | table | — | — | 截至12月31日止年度 截至8月31日止八個月 2023年 2024年 2024年 2025年 人民幣千元 人民幣千元 人民幣千元 人民幣千元 經營活動所得現金流量 除税前虧損 (93,423) (122,820) (60,417) (99,933) 就下列各項作出調整： 利息開支 8 2,280 9,379 5,853 7,532 銀行利息收入 5 (1,867) (1,618) (350) … |
| TBL_BS_COMPANY | 572 | text | — | — | 附註 於12月31日 於8月31日 2023年 2024年 2025年 人民幣千元 人民幣千元 人民幣千元 非流動資產 物業、廠房及設備 14 6,405 10,099 10,393 使用權資產 15 15,452 12,309 10,214 於附屬公司的投資 17 78,438 78,438 78,438 其他無形資產 18 - - 214 預付款項、其他應收款項及其他資產 18 531 - … |

#### 2.6.1 章节化上下文证据

- intent=`business_context` query=`翰思艾泰主营业务、核心在研管线、临床阶段、商业化进展及收入来源` → 无可用章节
- intent=`business_model` query=`公司业务模式、是否有产品销售收入、合作授权里程碑收入` → 无可用章节

_本次未调用章节化上下文检索，或未命中证据。_

### 2.7 工具调用链

- 耗时：`54.539s`

1. **`retrieve_finance`**
   ```json
   {"turn": 1, "arguments": {"reason": "获取翰思艾泰（18A生物科技公司）三张财务主表，用于后续指标抽取与门控判断。"}, "observation": {"ok": true, "source": "offline:/nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_finance.json", "tables": ["TBL_IS", "TBL_BS", "TBL_CF", "TBL_BS_COMPANY"], "tables_detail": [{"code": "TBL_IS", "nameZh": "合併損益表", "page": 562, "sourceType": "text", "excerpt": "截至12月31日止年度 截至8月31日止八個月\n\n附註 2023年 2024年 2024年 2025年\n人民幣千元 人民幣千元 人民幣千元 人民幣千元\n\n其他收入及收益 5 6,664 7,681 12,313 2,626\n研發成本 5 (46,663) (74,721) (50,523) (56,178)\n行政開支 6 (17,220) (46,192) (16,116) (27,436)\n其他", "nHits": 1}, {"code": "TBL_BS", "nameZh": "合併資產負債表", "page": 563, "sourceType": "text", "excerpt": "附註 於12月31日 於8月31日\n2023年 2024年 2025年\n人民幣千元 人民幣千元 人民幣千元\n\n非流動資產\n物業、廠房及設備 14 8,340 11,820 11,907\n使用權資產 15 15,661 12,309 10,525\n其他無形資產 16 558 447 587\n預付款項、其他應收款項及其他資產 18 531 330 330\n按公允價值計入損益（「按公允價值計入損益」）的", "nHits": 1}, {"code": "TBL_CF", "nameZh": "合併現金流量表", "page": 569, "sourceType": "table", "excerpt": "<table><tr><td rowspan=\"3\"></td><td colspan=\"2\">截至12月31日止年度</td><td colspan=\"2\">截至8月31日止八個月</td></tr><tr><td>2023年</td><td>2024年</td><td>2024年</td><td>2025年</td></tr><tr><td>人民幣千元</td><td>人民幣千元</td><t", "nHits": 1}, {"code": "TBL_BS_COMPANY", "nameZh": "公司層面資產負債表", "page": 572, "sourceType": "text", "excerpt": "附註 於12月31日 於8月31日\n2023年 2024年 2025年\n人民幣千元 人民幣千元 人民幣千元\n\n非流動資產\n物業、廠房及設備 14 6,405 10,099 10,393\n使用權資產 15 15,452 12,309 10,214\n於附屬公司的投資 17 78,438 78,438 78,438\n其他無形資產 18 - - 214\n預付款項、其他應收款項及其他資產 18 531 - ", "nHits": 1}], "skipped_fields": 0, "hint": "下一步可调用 extract_metrics"}, "duration_ms": 2733}
   ```
2. **`extract_metrics`**
   ```json
   {"turn": 2, "arguments": {"reason": "从翰思艾泰主表抽取标准化财务指标（收入、净亏损、现金流、现金及等价物、负债等）。"}, "observation": {"ok": true, "metric_keys": ["OTHER_INCOME", "RD_EXP", "SGA", "NET_LOSS", "NET_ASSETS", "CASH_EQ", "CV_PREF", "TOTAL_ASSETS", "TOTAL_LIAB", "CFO", "CFI", "CFF", "END_CASH"], "metric_keys_zh": [{"code": "OTHER_INCOME", "nameZh": "其他收入及收益"}, {"code": "RD_EXP", "nameZh": "研發費用"}, {"code": "SGA", "nameZh": "銷售及行政費用"}, {"code": "NET_LOSS", "nameZh": "期內虧損/利潤"}, {"code": "NET_ASSETS", "nameZh": "淨資產"}, {"code": "CASH_EQ", "nameZh": "現金及現金等價物"}, {"code": "CV_PREF", "nameZh": "可轉換可贖回優先股"}, {"code": "TOTAL_ASSETS", "nameZh": "總資產"}, {"code": "TOTAL_LIAB", "nameZh": "總負債"}, {"code": "CFO", "nameZh": "經營活動現金流淨額"}, {"code": "CFI", "nameZh": "投資活動現金流淨額"}, {"code": "CFF", "nameZh": "融資活動現金流淨額"}, {"code": "END_CASH", "nameZh": "年末現金餘額"}], "years": ["2023", "2024"], "metrics_summary": {"OTHER_INCOME": {"2023": 6664.0, "2024": 7681.0, "2024_i1": 12313.0, "2025_i1": 2626.0}, "NET_PROFIT_OR_LOSS": {"2023": -85160.0, "2024": -116922.0, "2024_i1": -48420.0, "2025_i1": -87438.0}, "CFO": {"2023": -51994.0, "2024": -104894.0, "2024_i1": -67918.0, "2025_i1": -59390.0}, "CASH_EQ": {"2023": 162000.0, "2024": 161214.0, "2025_i1": 150000.0}, "END_CASH": {"2023": 162000.0, "2024": 161214.0, "2024_i1": 181346.0, "2025_i1": 150000.0}, "TOTAL_ASSETS": {"2023": 586240.0, "2024": 501471.0, "2025_i1": 444298.0}, "TOTAL_LIAB": {"2023": 266659.0, "2024": 284867.0, "2025_i1": 299507.0}, "NET_ASSETS": {"2023": 319581.0, "2024": 216604.0, "2025_i1": 144791.0}}, "tables_detail": [{"code": "TBL_IS", "nameZh": "合併損益表", "page": 562, "sourceType": "text", "excerpt": "截至12月31日止年度 截至8月31日止八個月 附註 2023年 2024年 2024年 2025年 人民幣千元 人民幣千元 人民幣千元 人民幣千元 其他收入及收益 5 6,664 7,681 12,313 2,626 研發成本 5 (46,663) (74,721) (50,523) (56,178) 行政開支 6 "}, {"code": "TBL_BS", "nameZh": "合併資產負債表", "page": 563, "sourceType": "text", "excerpt": "附註 於12月31日 於8月31日 2023年 2024年 2025年 人民幣千元 人民幣千元 人民幣千元 非流動資產 物業、廠房及設備 14 8,340 11,820 11,907 使用權資產 15 15,661 12,309 10,525 其他無形資產 16 558 447 587 預付款項、其他應收款項及其他資產"}, {"code": "TBL_CF", "nameZh": "合併現金流量表", "page": 569, "sourceType": "table", "excerpt": "截至12月31日止年度 截至8月31日止八個月 2023年 2024年 2024年 2025年 人民幣千元 人民幣千元 人民幣千元 人民幣千元 經營活動所得現金流量 除税前虧損 (93,423) (122,820) (60,417) (99,933) 就下列各項作出調整： 利息開支 8 2,280 9,379 5,85"}, {"code": "TBL_BS_COMPANY", "nameZh": "公司層面資產負債表", "page": 572, "sourceType": "text", "excerpt": "附註 於12月31日 於8月31日 2023年 2024年 2025年 人民幣千元 人民幣千元 人民幣千元 非流動資產 物業、廠房及設備 14 6,405 10,099 10,393 使用權資產 15 15,452 12,309 10,214 於附屬公司的投資 17 78,438 78,438 78,438 其他無形資"}], "metric_note": "期內虧損/利潤(NET_LOSS/NET_PROFIT_OR_LOSS)：正數=盈利，負數=虧損。", "bs_reconcile": {"changed": false, "note": null}, "hint": "下一步可调用 derive_gates"}, "duration_ms": 2252}
   ```
3. **`derive_gates`**
   ```json
   {"turn": 3, "arguments": {"reason": "计算翰思艾泰的盈利门控、现金跑道门控及18A生物科技门控。"}, "observation": {"ok": true, "gates": {"is_unprofitable": true, "continuous_net_loss": true, "latest_full_year_loss": true, "skip_3_4": false, "skip_3_4_reason": null, "skip_2_4": false, "issuer_type": "18a", "is_biotech_18a": true, "net_series": {"2023": -85160.0, "2024": -116922.0}, "profitability_basis": "NET_LOSS/年內利潤 series; positive=profit", "profitability_known": true, "profitability_status": "unprofitable"}, "fast_path": {"eligible": false, "reason": null}, "hint": "若未盈利可 calc_cash_runway；非主表主题可 retrieve_context_evidence；否则 submit"}, "duration_ms": 4220}
   ```
4. **`calc_cash_runway`**
   ```json
   {"turn": 4, "arguments": {"reason": "翰思艾泰未盈利且连续亏损，测算现有现金及现金等价物的现金跑道。"}, "observation": {"ok": true, "cash_burn": {"skipped": false, "reason": null, "CASH_RUNWAY_MONTHS": 20.21, "BURN_RATE_MONTHLY": 7423.75, "END_CASH": 150000.0}}, "duration_ms": 1708}
   ```
5. **`retrieve_context_evidence`**
   ```json
   {"turn": 5, "arguments": {"intent": "business_context", "query": "翰思艾泰主营业务、核心在研管线、临床阶段、商业化进展及收入来源", "section_hint": "業務、概覽、風險因素", "top_k": 5}, "observation": {"ok": true, "doc_id": "hansiaitai", "intent": "business_context", "query": "翰思艾泰主营业务、核心在研管线、临床阶段、商业化进展及收入来源", "n": 0, "route": [], "hits": [], "hint": "完整证据已保存到 state；submit 时引用 page/section/excerpt 即可"}, "duration_ms": 4645}
   ```
6. **`retrieve_context_evidence`**
   ```json
   {"turn": 5, "arguments": {"intent": "business_model", "query": "公司业务模式、是否有产品销售收入、合作授权里程碑收入", "section_hint": "財務資料、業務模式", "top_k": 5}, "observation": {"ok": true, "doc_id": "hansiaitai", "intent": "business_model", "query": "公司业务模式、是否有产品销售收入、合作授权里程碑收入", "n": 0, "route": [], "hits": [], "hint": "完整证据已保存到 state；submit 时引用 page/section/excerpt 即可"}, "duration_ms": 4645}
   ```
7. **`submit_finance_report`**
   ```json
   {"turn": 6, "arguments": {}, "observation": {"ok": true, "finished": true, "risk_score": 50.0, "risk_level": "medium", "warnings": ["rules_floor_added:CONTINUOUS_LOSS", "rules_floor_added:CFO_NEGATIVE", "rules_floor_added:CASH_RUNWAY_12_24"], "summary": "", "rules_floor": {"rules_score": 50.0, "rules_score_deduped": 50.0, "llm_score": 0.0, "final_score": 50.0, "flags": {"continuous_net_loss": true, "latest_full_year_loss": true, "cfo_persistently_negative": true, "gp_margin_drop_gt_5pp": false, "runway_lt_12": false, "runway_12_24": true, "burn_yoy_up_gt_30": false}}}, "duration_ms": 18726}
   ```

### 2.8 分析结论

- 评分模式 **react+rules_floor**；风险分 **50.0**（medium）。门控：未盈利=`True`，跳过3.4=`False`（None），跳过2.4=`False`（None）。
- 模型 think 状态：`ok`（全文见推理日志 `[model_think]`）。
- 期内利润（NET_LOSS 字段存利润序列，正数=盈利）：2023=-85,160、2024=-116,922。
- 主表证据定位：TBL_IS@p562, TBL_BS@p563, TBL_CF@p569, TBL_BS_COMPANY@p572。
- 推理日志：`/nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/logs/翰思艾泰_finance_20260805_003602.log`

## 3. 法务合规 Agent

### 3.1 得分与分解

| 代码 | 加分 | 规则 | 指标值 | 说明 | 证据页 |
|------|------|------|--------|------|--------|
| RIGHTS_CLEANUP_INCOMPLETE | +20.0 | llm§legal_shareholder_rights | — | 特別權利（包括購回權）僅在上市申請提交時終止，但若上市失敗則自動恢復，未完全解除。 | 262 |
| REDEMPTION_HIGH | +18.0 | llm§legal_shareholder_rights | 138.5百萬元人民幣 | 贖回權觸發期限不足12個月（2025年12月31日），且贖回負債金額人民幣138.5百萬元，可能導致流動性風險及上市受阻。（覆盖规则同主题项） | 262 |
| IP_PATENT_REJECTION_RISK | +18.0 | llm§legal_contracts_and_ip | — | 核心產品相關的FcRn專利申請在中國被駁回，可能影響同族專利在其他司法權區的有效性，進而削弱核心技術的專利保護。 | 386 |
| REGULATORY_PENALTY | +15.0 | llm§legal_regulatory_litigation | — | 公司可能因社会保险基金及住房公积金供款不足而面临滞纳金或罚款，但公司已承诺补缴并制定内部监控政策，风险相对较小。 | 403 |
| GOVERNANCE_CONTROL_GT_50 | +10.0 | llm§legal_governance | 55.89 | 控股股東集團持股約55.89%，超過50%，對公司有重大影響力，可能阻礙控制權變更，損害少數股東利益。 | 115 |
| RELATED_PARTY_TERM | +8.0 | llm§legal_related_party | 協議有效期至2029年12月31日 | 關連交易協議期限超過三年，需依賴特殊情況豁免，存在合規風險。 | 416 |
| CONCENTRATION_DISCLOSURE | +6.0 | doc§3.3 | — | 存在客户/供应商集中度披露 | 28, 29 |
| PIPELINE_DISCLOSURE | +6.0 | doc§3.5 | — | 存在核心产品/管线进度披露 | 14, 16, 17, 20, 27 |

### 3.2 章节特征摘要

| 章节 | exists/skipped | 强度 | 关键字段 |
|------|----------------|------|----------|
| 3.1 | exists=None | — | — |
| 3.2 | exists=None | — | — |
| 3.3 | exists=None | — | — |
| 3.4 | exists=None | — | — |
| 3.5 | exists=None | — | — |
| 3.6 | exists=None | — | — |

### 3.3 召回证据明细

_无法务证据_

### 3.4 计分证据（score_breakdown）

#### `RIGHTS_CLEANUP_INCOMPLETE`（+20.0，llm§legal_shareholder_rights）

特別權利（包括購回權）僅在上市申請提交時終止，但若上市失敗則自動恢復，未完全解除。


#### `REDEMPTION_HIGH`（+18.0，llm§legal_shareholder_rights）

贖回權觸發期限不足12個月（2025年12月31日），且贖回負債金額人民幣138.5百萬元，可能導致流動性風險及上市受阻。（覆盖规则同主题项）


#### `IP_PATENT_REJECTION_RISK`（+18.0，llm§legal_contracts_and_ip）

核心產品相關的FcRn專利申請在中國被駁回，可能影響同族專利在其他司法權區的有效性，進而削弱核心技術的專利保護。


#### `REGULATORY_PENALTY`（+15.0，llm§legal_regulatory_litigation）

公司可能因社会保险基金及住房公积金供款不足而面临滞纳金或罚款，但公司已承诺补缴并制定内部监控政策，风险相对较小。


#### `GOVERNANCE_CONTROL_GT_50`（+10.0，llm§legal_governance）

控股股東集團持股約55.89%，超過50%，對公司有重大影響力，可能阻礙控制權變更，損害少數股東利益。


#### `RELATED_PARTY_TERM`（+8.0，llm§legal_related_party）

關連交易協議期限超過三年，需依賴特殊情況豁免，存在合規風險。


#### `CONCENTRATION_DISCLOSURE`（+6.0，doc§3.3）

存在客户/供应商集中度披露

- p28（table）：截至2023年及2024年12月31日止年度及截至2025年8月31日止八個月，五大供應商應佔總採購額分別約為人民幣16.3百萬元、人民幣28.6百萬元及人民幣23.3百萬元，分別佔我們總採購額約51.8%、37.4%及45.5%。同期，單一最大供應商應佔採購額分別約為人民幣6.4百萬元、人民幣7.8百萬元及人民幣6.3百萬元，分別佔我們總採購額約20.4%、10.2%及12.4%。
- p28（table）：截至2023年及2024年12月31日止年度及截至2025年8月31日止八個月，五大供應商應佔總採購額分別約為人民幣16.3百萬元、人民幣28.6百萬元及人民幣23.3百萬元，分別佔我們總採購額約51.8%、37.4%及45.5%。同期，單一最大供應商應佔採購額分別約為人民幣6.4百萬元、人民幣7.8百萬元及人民幣6.3百萬元，分別佔我們總採購額約20.4%、10.2%及12.4%。
- p29（table）：於往績記錄期間各期間，概無五大供應商為我們的關聯方。概無董事或其聯繫人或（據董事所知）任何擁有本公司股本5%以上的股東於截至2023年及2024年12月31日止年度以及截至2025年8月31日止八個月在任何五大供應商中擁有任何權益。
- p29（table）：於往績記錄期間各期間，概無五大供應商為我們的關聯方。概無董事或其聯繫人或（據董事所知）任何擁有本公司股本5%以上的股東於截至2023年及2024年12月31日止年度以及截至2025年8月31日止八個月在任何五大供應商中擁有任何權益。

#### `PIPELINE_DISCLOSURE`（+6.0，doc§3.5）

存在核心产品/管线进度披露

- p16（text）：除HX301乃自Onconova Therapeutics, Inc.授權引進外，我們的管線候選產品全部由我們自主研發。我們構建產品管線，旨在利用先天及適應性免疫實現潛在協同效應。我們的產品管線旨在解決現有檢查點抑制劑免疫療法的局限性，包括免疫抑制性腫瘤微環境致使「冷腫瘤」響應有限以及其他未獲滿足的醫療需求，從而為各種癌症患者及其他疾病適應症患者帶來臨床裨益。截至最後實際可行日期，我們已建立由10
- p17（text）：我們根據相關方案及批准進行HX009的臨床研究。於2024年9月，我們的中國法律顧問連同獨家保薦人及其法律顧問在北京與國家藥監局藥審中心臨床試驗管理辦公室的審查員進行了面對面訪談，期間已確認（其中包括）我們已完成一項常規I期臨床研究，且HX009的國家藥監局一次性傘式批准允許本公司在III期研究之前進行HX009-I-01中國研究下的臨床研究，而無需再次獲得國家藥監局的監管批准。有關詳情請參閱本招
- p20（text）：我們的核心產品HX009是一種同時靶向CD47及PD-1的雙特異性抗體融合蛋白。根據弗若斯特沙利文報告，截至最後實際可行日期，HX009的臨床試驗進展在同類CD47靶向雙特異性抗體／雙功能融合蛋白產品中處於全球領先地位。
- p27（text）：我們的研發團隊通常負責核心產品及其他管線產品的全球開發。我們的研發團隊有能力在中國及其他司法權區同時開展不同開發階段的臨床項目。彼等平均擁有10年左右的行業工作經驗，且幾乎全部擁有本科或以上學歷。就自主發現及開發的候選藥物而言，我們與臨床開發團隊共同開展藥物發現、質量保證及臨床活動，其中包括：(i)協調所有臨床開發工作；(ii)制定臨床試驗的關鍵要素；(iii)安排及協調合適的CRO參與臨床試驗，
- p14（text）：截至最後實際可行日期，我們已開發十種候選藥物組成的管線，包括我們的核心產品HX009及兩種主要產品HX044及HX301，其中有八種針對腫瘤科的候選藥物及兩種針對自身免疫疾病的候選藥物。截至最後實際可行日期，我們的核心產品以及主要產品分別在中國及澳大利亞進行臨床試驗。下圖概述截至最後實際可行日期我們管線產品的開發狀態。

### 3.5 工具调用链

- 耗时：`94.161s`

1. **`retrieve_legal`**
   ```json
   {"turn": 1, "arguments": {"reason": "啟動翰思艾泰港股IPO法務穿透審查，初始化招股書證據包以進行後續五項專項合規審查。"}, "observation": {"ok": true, "source": "offline:/nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_legal.json", "fields": ["REDEMPTION_CLAUSE", "RELATED_PARTY", "CONCENTRATION", "CASH_BURN_PRESSURE", "PIPELINE_RISK", "PRE_IPO_VALUATION"], "grep_hits": 0, "grep_pages_sample": [], "has_evidence_by_field": true, "skills_available": ["legal_governance", "legal_shareholder_rights", "legal_related_party", "legal_contracts_and_ip", "legal_regulatory_litigation"], "search_quota": 2, "search_used": 0, "hint": "下一步逐个调用 run_legal_skill（共5个）；search_legal_evidence 全程配额≤2 次，证据不足时精选补检，rule_checks 后尽快 submit"}, "duration_ms": 2032}
   ```
2. **`run_legal_skill`**
   ```json
   {"turn": 2, "arguments": {"skill_name": "legal_governance", "reason": "審查翰思艾泰的股權結構、境內外架構重組、董事會與公司治理安排，識別紅籌架構及治理合規風險。", "focus_hint": "紅籌VIE架構/股權變動/董事會構成/表決權差異"}, "observation": {"ok": true, "skill": "legal_governance", "exists": true, "confidence": "high", "n_risk_points": 3, "risk_points": [{"code": "GOVERNANCE_CONTROL_GT_50", "level": "high", "confidence": "high", "evidence_page": 115, "description": "控股股東集團持股約55.89%，超過50%，對公司有重大影響力，可能阻礙控制權變更，損害少數股東利益。"}, {"code": "GOVERNANCE_CONCERT_PARTY", "level": "medium", "confidence": "high", "evidence_page": 254, "description": "與武漢瀚中及杭州甘明訂立一致行動協議，以維持對杭州翰思的控制權，協議尚未終止，可能影響公司治理的獨立性。"}, {"code": "GOVERNANCE_BOARD_INDEPENDENCE", "level": "medium", "confidence": "high", "evidence_page": 272, "description": "董事會結構中，執行董事肖女士持股極少，且控股股東影響力大，可能影響董事會獨立性。"}], "features": {"controlling_shareholder": "蔡張生物科技、翰思生物醫藥（香港）及武漢翰思", "control_pct": 55.89, "concert_party": true, "ab_shares": false, "board_note": "董事會結構未在原文中詳細描述，但存在執行董事肖女士持股0.01%。"}, "negative_findings_n": 1, "evidence_pages": [80, 81, 115, 254, 272], "search_quota": 2, "search_used": 0, "error": null, "hint": "证据充分，可继续下一个 skill"}, "duration_ms": 3176}
   ```
3. **`run_legal_skill`**
   ```json
   {"turn": 3, "arguments": {"focus_hint": "優先股/對賭贖回/投資者特殊權利/清算優先權", "reason": "審查翰思艾泰上市前的優先股、對賭贖回條款及投資者特殊權利的清理情況，識別上市後失效安排與剩餘義務風險。", "skill_name": "legal_shareholder_rights"}, "observation": {"ok": true, "skill": "legal_shareholder_rights", "exists": true, "confidence": "high", "n_risk_points": 3, "risk_points": [{"code": "REDEMPTION_HIGH", "level": "high", "confidence": "high", "evidence_page": 262, "description": "贖回權觸發期限不足12個月（2025年12月31日），且贖回負債金額人民幣138.5百萬元，可能導致流動性風險及上市受阻。"}, {"code": "REDEMPTION_MEDIUM", "level": "medium", "confidence": "high", "evidence_page": 497, "description": "贖回負債金額佔流動負債淨額比例高，且贖回權未完全終止，存在流動性不足風險。"}, {"code": "RIGHTS_CLEANUP_INCOMPLETE", "level": "high", "confidence": "high", "evidence_page": 262, "description": "特別權利（包括購回權）僅在上市申請提交時終止，但若上市失敗則自動恢復，未完全解除。"}], "features": {"exists_redemption": true, "trigger_condition": "上市申請被撤回或駁回、中國證監會備案被駁回、或未能於2025年12月31日前完成上市（以較早者為準）", "redemption_price_or_rate": "按贖回金額的攤銷成本確認，未明確利率", "amount": "人民幣138.5百萬元", "remaining_months": 4, "rights_cleared_pre_ipo": true, "pre_ipo_rounds": 3}, "negative_findings_n": 1, "evidence_pages": [80, 262, 271, 477, 497], "search_quota": 2, "search_used": 0, "error": null, "hint": "证据充分，可继续下一个 skill"}, "duration_ms": 2145}
   ```
4. **`run_legal_skill`**
   ```json
   {"turn": 4, "arguments": {"focus_hint": "關連交易/持續關連交易/非豁免/獨立股東批准", "reason": "審查翰思艾泰的關連交易及持續關連交易安排，識別未獲豁免、定價不公允或未經獨立股東批准的風險。", "skill_name": "legal_related_party"}, "observation": {"ok": true, "skill": "legal_related_party", "exists": true, "confidence": "high", "n_risk_points": 3, "risk_points": [{"code": "RELATED_PARTY_EXEMPTION", "level": "low", "confidence": "high", "evidence_page": 424, "description": "關連交易獲完全豁免，但依賴豁免條件，若未來比例上升可能需重新合規。"}, {"code": "RELATED_PARTY_TERM", "level": "medium", "confidence": "high", "evidence_page": 416, "description": "關連交易協議期限超過三年，需依賴特殊情況豁免，存在合規風險。"}, {"code": "RELATED_PARTY_DEPENDENCE", "level": "low", "confidence": "high", "evidence_page": 416, "description": "發行人依賴關連方提供穩定性測試服務，因缺乏設備，存在潛在依賴風險。"}], "features": {"parties": ["中美華世通（關連方）", "發行人"], "txn_types": ["採購（原材料供應）", "服務（穩定性測試）"], "max_ratio_pct": 5, "ratio_rising": false, "waiver": "完全豁免（低於5%及300萬港元）", "fair_price": "董事及獨家保薦人認為公平合理", "dependency": false}, "negative_findings_n": 2, "evidence_pages": [415, 416, 424, 425], "search_quota": 2, "search_used": 0, "error": null, "hint": "证据充分，可继续下一个 skill"}, "duration_ms": 2012}
   ```
5. **`run_legal_skill`**
   ```json
   {"turn": 5, "arguments": {"focus_hint": "重大合約/依賴單一供應商或客戶/知識產權保護/許可安排", "reason": "審查翰思艾泰的重大合約、供應商與客戶集中度及知識產權保護情況，識別合同與IP風險。", "skill_name": "legal_contracts_and_ip"}, "observation": {"ok": true, "skill": "legal_contracts_and_ip", "exists": true, "confidence": "high", "n_risk_points": 5, "risk_points": [{"code": "IP_PATENT_REJECTION_RISK", "level": "high", "confidence": "high", "evidence_page": 386, "description": "核心產品相關的FcRn專利申請在中國被駁回，可能影響同族專利在其他司法權區的有效性，進而削弱核心技術的專利保護。"}, {"code": "IP_PATENT_MAINTENANCE_RISK", "level": "medium", "confidence": "high", "evidence_page": 93, "description": "專利維護需定期繳納費用並遵守程序，若未按時繳費或回應官方行動，可能導致專利失效，使競爭者進入市場。"}, {"code": "IP_THIRD_PARTY_INFRINGEMENT_RISK", "level": "medium", "confidence": "high", "evidence_page": 92, "description": "存在第三方侵犯或盜用知識產權的風險，且可能無法及時發現或採取行動，影響競爭優勢。"}, {"code": "IP_EMPLOYEE_DISPUTE_RISK", "level": "medium", "confidence": "high", "evidence_page": 98, "description": "前僱員席先生可能與公司就專利產生潛在糾紛，可能影響知識產權的穩定性。"}, {"code": "IP_FTO_SCOPE_LIMITATION", "level": "low", "confidence": "high", "evidence_page": 386, "description": "自由運營分析僅在中國進行，未覆蓋所有目標市場，且HX044尚無FTO分析，存在潛在侵權風險。"}], "features": {"material_contracts": ["HX008股權轉讓協議（與中山康方合作）", "專利轉讓（杭州翰思至泰州翰中）"], "exclusive_deals": false, "core_tech_self_owned": true, "license_in": false, "ip_note": "核心產品專利自主研發，但FcRn專利申請在中國被駁回，可能影響同族專利在其他國家的有效性。"}, "negative_findings_n": 2, "evidence_pages": [74, 92, 93, 98, 381, 386, 407], "search_quota": 2, "search_used": 0, "error": null, "hint": "证据充分，可继续下一个 skill"}, "duration_ms": 1856}
   ```
6. **`run_legal_skill`**
   ```json
   {"turn": 6, "arguments": {"focus_hint": "監管處罰/訴訟仲裁/醫療糾紛/產品責任", "reason": "審查翰思艾泰及其附屬公司的監管處罰、訴訟仲裁及潛在醫療產品責任風險。", "skill_name": "legal_regulatory_litigation"}, "observation": {"ok": true, "skill": "legal_regulatory_litigation", "exists": true, "confidence": "high", "n_risk_points": 5, "risk_points": [{"code": "REGULATORY_PENALTY", "level": "medium", "confidence": "high", "evidence_page": 403, "description": "公司可能因社会保险基金及住房公积金供款不足而面临滞纳金或罚款，但公司已承诺补缴并制定内部监控政策，风险相对较小。"}, {"code": "REGULATORY_COMPLIANCE_RISK", "level": "medium", "confidence": "high", "evidence_page": 237, "description": "公司面临美国FDA及中国监管机构的严格监管，若未能遵守相关法规，可能遭受行政处罚、产品召回等制裁。"}, {"code": "LICENSE_MISSING", "level": "low", "confidence": "high", "evidence_page": 406, "description": "未发现关键许可证缺失，公司已遵守相关法律法规。"}, {"code": "LITIGATION_MAJOR", "level": "low", "confidence": "high", "evidence_page": 406, "description": "未涉及重大诉讼、仲裁或行政程序，无重大未决诉讼。"}, {"code": "HUMAN_GENETIC_RESOURCE_COMPLIANCE", "level": "medium", "confidence": "high", "evidence_page": 86, "description": "公司面临中国人类遗传资源管理的合规风险，可能因违反相关法规而受到行政处罚。"}], "features": {"penalties": ["社会保险基金及住房公积金供款可能被征收滞纳金或罚款"], "investigations": ["无具体调查事项"], "licenses_missing": ["无关键许可证缺失"], "major_litigation": false}, "negative_findings_n": 2, "evidence_pages": [83, 85, 86, 87, 233, 237, 403, 406], "search_quota": 2, "search_used": 0, "error": null, "hint": "证据充分，可继续下一个 skill"}, "duration_ms": 1734}
   ```
7. **`run_rule_checks`**
   ```json
   {"turn": 7, "arguments": {"reason": "交叉核對五項專項審查的風險點與規則引擎命中，識別覆蓋缺口後決定是否需補充檢索。"}, "observation": {"ok": true, "rules_score": 51.0, "rules_level": "medium", "flags": {"redemption_high": false, "redemption_medium": true, "related_party_ratio_gt_30": false, "related_party_rising": false, "concentration_high": false, "pipeline_high": false, "valuation_inversion": false}, "breakdown": [{"code": "REDEMPTION_MEDIUM", "delta": 12.0, "rule_ref": "doc§3.1"}, {"code": "RELATED_PARTY_DISCLOSURE", "delta": 15.0, "rule_ref": "doc§3.2"}, {"code": "CONCENTRATION_DISCLOSURE", "delta": 12.0, "rule_ref": "doc§3.3"}, {"code": "PIPELINE_DISCLOSURE", "delta": 12.0, "rule_ref": "doc§3.5"}], "coverage_hints": [], "search_quota": 0, "search_used": 0, "hint": "无覆盖缺口。下一动作必须 submit_legal_report，禁止再 search。"}, "duration_ms": 10978}
   ```
8. **`None`**
   ```json
   {"turn": 8, "status": "no_tool_call", "content": ""}
   ```

### 3.6 分析结论

- 风险分 **66.54795583744**（high）。打分来自披露基础分或规则命中（见 score_breakdown）。
- 3.1 对赌/赎回：exists=`None`，证据强度=`None`
- 3.2 关联交易：exists=`None`，占比=`None`。
- 3.3 集中度：exists=`None`，证据页=None。

## 4. 改进建议

1. **[已做] 财务 LLM 主路径**：retrieve → extract_metrics → gates → analyze_finance(单次四维 LLM) → 可解释评分；规则打分降为 fallback（`--finance-rules-only`）。
2. **[已做] Gemma4 reasoning**：OpenRouter `reasoning.enabled`；日志区分 `[model_think]` / `[structured_reasoning]`。
3. **[已做] 推理日志落盘**：`logs/{doc}_{agent}_{ts}.log` + `.jsonl`（时间/文档/流程/工具skills/过程/结果/推理链）。
4. **[已做] 财务 BS 交叉校验**：若 TOTAL_ASSETS < NET_ASSETS，用 NET+LIAB 回填。
5. **法务检索源**：可用 `--use-live-retrieval`；`--use-llm` 做法务结构化增强。

---

_本报告由 `scripts/generate_analysis_report.py` 根据 Agent 结构化输出自动生成。_
