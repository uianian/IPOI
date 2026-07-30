# 翰思艾泰 — 财务/法务 Agent 结果分析报告

- 生成时间：2026-07-25 19:14:26
- 招股书：`03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf`
- doc_id：`hansiaitai`
- 参考基本面融合分：`53.2` （legal×0.45 + finance×0.55；总控未启用）
- 财务评分模式：`react+rules_floor`
- 推理日志：`/nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/logs/翰思艾泰_finance_20260725_191330.log`
- 说明：reference_fundamental_score = legal*0.45 + finance*0.55; master/cross_agent_features 为本轮占位，总控辩论未启用

## 1. 总览

| Agent | 风险分 (0-100↑风险) | 等级 | 摘要 |
|-------|---------------------|------|------|
| 财务穿透 | **55.0** | medium | 翰思艾泰为典型18A生物科技公司，虽持续亏损且CFO为负，但现金跑道充足（约20个月），整体财务风险可控（注：规则托底后综合评分 55，等级 medium，叙述以该等级为准。） |
| 法务合规 | **51.0** | medium | 法务 3.1/3.2/3.3 抽取完成；3.5=启用；风险分 51.0 (medium) |

## 2. 财务穿透 Agent

### 2.1 得分与分解

| 代码 | 加分 | 规则 | 指标值 | 说明 | 证据页 |
|------|------|------|--------|------|--------|
| CONTINUOUS_LOSS | +25.0 | doc§2.1 | — | （规则托底上调） | 562 |
| CFO_NEGATIVE | +15.0 | doc§2.3 | — | （规则托底上调） | 569 |
| NET_ASSETS_DECLINE | +5.0 | SOLVENCY-01 | 319.58M -> 144.79M | 净资产规模持续下降 | 0 |
| CASH_RUNWAY_12_24 | +10.0 | doc§3.4 | — | （规则托底） | 563 |

### 2.2 四维分析（LLM）

#### `profitability_growth` — status=`analyzed`

公司处于典型的18A生物科技研发阶段，尚未实现盈利。2023年及2024年分别录得净亏损8516.0万及1.17亿元，亏损规模呈扩大趋势。


#### `cash_flow` — status=`analyzed`

经营活动现金流（CFO）持续为负且流出量增加（2024年为-1.05亿元），依赖融资维持运营。但现金储备充足，截至2025年一季度末现金及等价物约1.5亿元，测算现金跑道约为20.2个月，短期生存压力较低。


#### `solvency` — status=`analyzed`

资产负债表整体稳健，净资产虽从2023年的3.20亿元下降至2025年一季度的1.45亿元，但仍保持正值，偿债能力尚可。


#### `business_context` — status=`analyzed`

核心业务聚焦免疫肿瘤学，通过自主研发及外部许可（如与Onconova就narazaciclib的许可协议）构建管线。商业化能力依赖于后续临床研究的进展及监管审批。



### 2.3 推理链

**[structured_reasoning]**

发行人为18A生物科技公司，处于研发高投入期，连续两年亏损且CFO为负，符合行业特征。虽然现金跑道（20.2个月）充足，但由于持续亏损且净资产呈下降趋势，判定为中低风险（注：规则托底后综合评分 55，等级 medium，叙述以该等级为准。）

**[model_think 摘录]**（全文见 logs）

> I have enough information to construct the report.  **Summary of Findings:** 1. **Profitability & Growth**: Unprofitable. Net losses increased from 85.16M in 2023 to 116.92M in 2024. This is typical for 18A biotech companies but still a risk. 2. **Cash Flow**: CFO is negative and worsening (-51.99M in 2023 to -104.89M in 2024). 3. **Solvency**: Net assets are positive but decreasing (319.58M in 2023 -> 216.60M in 2024 -> 144.79M in 2025_i1). 4. **Cash Runway**: ~20.2 months, which is generally a

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

- intent=`business_model` query=`翰思艾泰的商业模式、核心产品管线及研发进度` → business@p277-414, risk_factors@p73-126, summary@p12-54

| 意图章节 | 页码 | 类型 | 分数 | 匹配词 | 摘录 |
|---|---:|---|---:|---|---|
| business | 315 | text | 1.5334 | — | 核心產品及主要產品準備中的臨床研究摘要 |
| business | 376 | text | 1.4 | — | 許可及開發：(i) Onconova向杭州翰思授予在大中華區開發及商業化narazaciclib的獨家許可，而杭州翰思向Onconova授予在大中華區以外地區開發及製造narazaciclib的權利。(ii)根據Onconova共同開發協議，杭州翰思負責所有開發活動，包括在大中華區開展臨床試驗及取得監管批准，而Onconova有權就HX301的任何臨床試驗的設計及實施進行審查並發表意見。(iii)臨床前研究的設計、臨床試驗方案及終點的設計將交由雙方成立的聯合指導委員會（「聯合 |
| business | 380 | text | 1.3877 | — | 終止：倘另一方嚴重不履行其義務，或另一方申請破產、重整、清算或接管，或倘其將大部分資產轉讓予債權人，則該協議授予雙方終止權。根據該協議，倘杭州翰思未作出商業上合理的努力以將HX301商業化，或杭州翰思或其聯屬公司對任何Onconova專利的有效性提出質疑、啟動異議程序或反對任何專利延期，則Onconova可終止協議。杭州翰思亦可透過向Onconova提供45天事先書面通知終止協議。終止協議將導致(i)即時終止授予杭州翰思的權利及許可；(ii)向Onconova免費轉讓與HX3 |
| summary | 27 | text | 1.382 | — | 我們的研發團隊由高水平專業人士組成，彼等對腫瘤免疫學、癌症生物學、自身免疫疾病以及轉化醫學及臨床科學擁有廣泛知識及深刻理解。彼等一直引領疾病相關各種通路的調節化合物發現工作，令我們在滿足複雜疾病的臨床需求方面具有獨特優勢。我們的研發團隊由數位知名科學家領導，彼等擁有豐富的藥物開發經驗。截至最後實際可行日期，在我們的董事長兼執行董事張博士及首席商務官唐博士的監督下及在我們的首席執行官兼首席科學家李博士的領導下，我們的研發團隊由20名成員組成，涵蓋生物化學、生物學、藥理學及臨床科 |
| summary | 16 | text | 1.38 | — | 我們的核心業務模式涉及開發強大的免疫腫瘤項目。我們開發了HX008，一種經證實具有較長半衰期靶向PD-1的單克隆抗體，其於往績記錄期間前轉讓且其後於2022年商業化。於往績記錄期間，我們主要通過在免疫腫瘤學管線中創造雙功能或多功能分子進行創新，包括「PD-1 plus」分子HX009（我們的核心產品）及HX016-9；「CTLA-4 plus」分子HX044（我們的一種主要產品）；及「PD-L1 plus」分子HX016-7。我們使用我們的專有VersatiBody平台（一種 |

### 2.7 工具调用链

- 耗时：`39.399s`

1. **`retrieve_finance`**
   ```json
   {"turn": 1, "arguments": {"reason": "开始财务穿透分析，首先需要检索三张财务主表以获取基础数据。"}, "observation": {"ok": true, "source": "offline:/nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_finance.json", "tables": ["TBL_IS", "TBL_BS", "TBL_BS_COMPANY", "TBL_CF"], "skipped_fields": 0, "hint": "下一步可调用 extract_metrics"}, "duration_ms": 6342}
   ```
2. **`extract_metrics`**
   ```json
   {"turn": 2, "arguments": {"reason": "从检索到的财务主表中抽取标准指标，用于后续的门控计算和风险评估。"}, "observation": {"ok": true, "metric_keys": ["OTHER_INCOME", "RD_EXP", "SGA", "NET_LOSS", "NET_ASSETS", "CASH_EQ", "CV_PREF", "TOTAL_ASSETS", "TOTAL_LIAB", "CFO", "CFI", "CFF", "END_CASH"], "years": ["2023", "2024"], "metrics_summary": {"OTHER_INCOME": {"2023": 6664.0, "2024": 7681.0, "2024_i1": 12313.0, "2025_i1": 2626.0}, "NET_PROFIT_OR_LOSS": {"2023": -85160.0, "2024": -116922.0, "2024_i1": -48420.0, "2025_i1": -87438.0}, "CFO": {"2023": -51994.0, "2024": -104894.0, "2024_i1": -67918.0, "2025_i1": -59390.0}, "CASH_EQ": {"2023": 162000.0, "2024": 161214.0, "2025_i1": 150000.0}, "END_CASH": {"2023": 162000.0, "2024": 161214.0, "2024_i1": 181346.0, "2025_i1": 150000.0}, "TOTAL_ASSETS": {"2023": 586240.0, "2024": 501471.0, "2025_i1": 444298.0}, "TOTAL_LIAB": {"2023": 266659.0, "2024": 284867.0, "2025_i1": 299507.0}, "NET_ASSETS": {"2023": 319581.0, "2024": 216604.0, "2025_i1": 144791.0}}, "metric_note": "NET_PROFIT_OR_LOSS 为底线利润/亏损字段；正数=盈利，负数=亏损。", "bs_reconcile": {"changed": false, "note": null}, "hint": "下一步可调用 derive_gates"}, "duration_ms": 3168}
   ```
3. **`derive_gates`**
   ```json
   {"turn": 3, "arguments": {"reason": "根据提取的指标计算盈利状态和现金跑道门控，决定是否需要执行 calc_cash_runway。"}, "observation": {"ok": true, "gates": {"is_unprofitable": true, "continuous_net_loss": true, "latest_full_year_loss": true, "skip_3_4": false, "skip_3_4_reason": null, "skip_2_4": false, "issuer_type": "18a", "is_biotech_18a": true, "net_series": {"2023": -85160.0, "2024": -116922.0}, "profitability_basis": "NET_LOSS/年內利潤 series; positive=profit", "profitability_known": true, "profitability_status": "unprofitable"}, "fast_path": {"eligible": false, "reason": null}, "hint": "若未盈利可 calc_cash_runway；非主表主题可 retrieve_context_evidence；否则 submit"}, "duration_ms": 1772}
   ```
4. **`calc_cash_runway`**
   ```json
   {"turn": 4, "arguments": {"reason": "公司处于未盈利状态且为18A生物科技公司，需测算现金跑道以评估生存风险。"}, "observation": {"ok": true, "cash_burn": {"skipped": false, "reason": null, "CASH_RUNWAY_MONTHS": 20.21, "BURN_RATE_MONTHLY": 7423.75, "END_CASH": 150000.0}}, "duration_ms": 1716}
   ```
5. **`retrieve_context_evidence`**
   ```json
   {"turn": 5, "arguments": {"intent": "business_model", "query": "翰思艾泰的商业模式、核心产品管线及研发进度", "reason": "作为18A公司，其风险核心在于研发管线的进度和商业化潜力，需补充非财务证据。"}, "observation": {"ok": true, "doc_id": "hansiaitai", "intent": "business_model", "query": "翰思艾泰的商业模式、核心产品管线及研发进度", "n": 5, "route": [{"section_id": "business", "section_title": "業務", "start_page": 277, "end_page": 414, "confidence": 0.95}, {"section_id": "risk_factors", "section_title": "風險因素", "start_page": 73, "end_page": 126, "confidence": 0.95}, {"section_id": "summary", "section_title": "概要", "start_page": 12, "end_page": 54, "confidence": 0.95}], "hits": [{"page": 315, "section_id": "business", "source_type": "text", "score": 1.5334, "matched_terms": [], "excerpt": "核心產品及主要產品準備中的臨床研究摘要"}, {"page": 376, "section_id": "business", "source_type": "text", "score": 1.4, "matched_terms": [], "excerpt": "許可及開發：(i) Onconova向杭州翰思授予在大中華區開發及商業化narazaciclib的獨家許可，而杭州翰思向Onconova授予在大中華區以外地區開發及製造narazaciclib的權利。(ii)根據Onconova共同開發協議"}, {"page": 380, "section_id": "business", "source_type": "text", "score": 1.3877, "matched_terms": [], "excerpt": "終止：倘另一方嚴重不履行其義務，或另一方申請破產、重整、清算或接管，或倘其將大部分資產轉讓予債權人，則該協議授予雙方終止權。根據該協議，倘杭州翰思未作出商業上合理的努力以將HX301商業化，或杭州翰思或其聯屬公司對任何Onconova專利的"}, {"page": 27, "section_id": "summary", "source_type": "text", "score": 1.382, "matched_terms": [], "excerpt": "我們的研發團隊由高水平專業人士組成，彼等對腫瘤免疫學、癌症生物學、自身免疫疾病以及轉化醫學及臨床科學擁有廣泛知識及深刻理解。彼等一直引領疾病相關各種通路的調節化合物發現工作，令我們在滿足複雜疾病的臨床需求方面具有獨特優勢。我們的研發團隊由數"}, {"page": 16, "section_id": "summary", "source_type": "text", "score": 1.38, "matched_terms": [], "excerpt": "我們的核心業務模式涉及開發強大的免疫腫瘤項目。我們開發了HX008，一種經證實具有較長半衰期靶向PD-1的單克隆抗體，其於往績記錄期間前轉讓且其後於2022年商業化。於往績記錄期間，我們主要通過在免疫腫瘤學管線中創造雙功能或多功能分子進行創"}], "hint": "完整证据已保存到 state；submit 时引用 page/section/excerpt 即可"}, "duration_ms": 3982}
   ```
6. **`submit_finance_report`**
   ```json
   {"turn": 6, "arguments": {"dimensions": [{"analysis": "公司处于典型的18A生物科技研发阶段，尚未实现盈利。2023年及2024年分别录得净亏损8516.0万及1.17亿元，亏损规模呈扩大趋势。", "dimension": "profitability_growth"}, {"analysis": "经营活动现金流（CFO）持续为负且流出量增加（2024年为-1.05亿元），依赖融资维持运营。但现金储备充足，截至2025年一季度末现金及等价物约1.5亿元，测算现金跑道约为20.2个月，短期生存压力较低。", "dimension": "cash_flow"}, {"analysis": "资产负债表整体稳健，净资产虽从2023年的3.20亿元下降至2025年一季度的1.45亿元，但仍保持正值，偿债能力尚可。", "dimension": "solvency"}, {"analysis": "核心业务聚焦免疫肿瘤学，通过自主研发及外部许可（如与Onconova就narazaciclib的许可协议）构建管线。商业化能力依赖于后续临床研究的进展及监管审批。", "dimension": "business_context"}], "negative_findings": [{"code": "CONTINUOUS_NET_LOSS", "rule_ref": "18A-PROFIT-01"}, {"code": "NEGATIVE_CFO", "rule_ref": "CASH-FLOW-02"}], "reasoning": "发行人为18A生物科技公司，处于研发高投入期，连续两年亏损且CFO为负，符合行业特征。虽然现金跑道（20.2个月）充足，但由于持续亏损且净资产呈下降趋势，判定为中低风险。", "risk_level": "low", "risk_points": [{"code": "NET_LOSS_CONTINUOUS", "evidence_page": 0, "level": "medium", "metric_value": "-116.92M (2024)", "rule_ref": "18A-PROFIT-01"}, {"code": "CFO_NEGATIVE", "evidence_page": 0, "level": "low", "metric_value": "-104.89M (2024)", "rule_ref": "CASH-FLOW-02"}], "risk_score": 30, "score_breakdown": [{"code": "NET_LOSS_CONTINUOUS", "delta": 15, "evidence_page": 0, "metric_value": "-116.92M (2024)", "note": "连续两年净亏损且规模扩大", "rule_ref": "18A-PROFIT-01"}, {"code": "CFO_NEGATIVE", "delta": 10, "evidence_page": 0, "metric_value": "-104.89M (2024)", "note": "经营活动现金流持续流出", "rule_ref": "CASH-FLOW-02"}, {"code": "NET_ASSETS_DECLINE", "delta": 5, "evidence_page": 0, "metric_value": "319.58M -> 144.79M", "note": "净资产规模持续下降", "rule_ref": "SOLVENCY-01"}], "summary": "翰思艾泰为典型18A生物科技公司，虽持续亏损且CFO为负，但现金跑道充足（约20个月），整体财务风险可控。"}, "observation": {"ok": true, "finished": true, "risk_score": 55.0, "risk_level": "medium", "warnings": ["rules_floor_raised:CONTINUOUS_LOSS", "rules_floor_raised:CFO_NEGATIVE", "rules_floor_added:CASH_RUNWAY_12_24", "narrative_aligned:reasoning"], "summary": "翰思艾泰为典型18A生物科技公司，虽持续亏损且CFO为负，但现金跑道充足（约20个月），整体财务风险可控。", "rules_floor": {"rules_score": 50.0, "rules_score_deduped": 55.0, "llm_score": 30.0, "final_score": 55.0, "flags": {"continuous_net_loss": true, "latest_full_year_loss": true, "cfo_persistently_negative": true, "gp_margin_drop_gt_5pp": false, "runway_lt_12": false, "runway_12_24": true, "burn_yoy_up_gt_30": false}}}, "duration_ms": 21315}
   ```

### 2.8 分析结论

- 评分模式 **react+rules_floor**；风险分 **55.0**（medium）。门控：未盈利=`True`，跳过3.4=`False`（None），跳过2.4=`False`（None）。
- 模型 think 状态：`ok`（全文见推理日志 `[model_think]`）。
- 结构化推理摘要：发行人为18A生物科技公司，处于研发高投入期，连续两年亏损且CFO为负，符合行业特征。虽然现金跑道（20.2个月）充足，但由于持续亏损且净资产呈下降趋势，判定为中低风险（注：规则托底后综合评分 55，等级 medium，叙述以该等级为准。）
- LLM 摘要：翰思艾泰为典型18A生物科技公司，虽持续亏损且CFO为负，但现金跑道充足（约20个月），整体财务风险可控。
- 期内利润（NET_LOSS 字段存利润序列，正数=盈利）：2023=-85,160、2024=-116,922。
- 主表证据定位：TBL_IS@p562, TBL_BS@p563, TBL_CF@p569, TBL_BS_COMPANY@p572。
- 推理日志：`/nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/logs/翰思艾泰_finance_20260725_191330.log`

### 2.9 阴性发现（低风险说明）

- **CONTINUOUS_NET_LOSS**（18A-PROFIT-01）：None
- **NEGATIVE_CFO**（CASH-FLOW-02）：None

## 3. 法务合规 Agent

### 3.1 得分与分解

| 代码 | 加分 | 规则 | 指标值 | 说明 | 证据页 |
|------|------|------|--------|------|--------|
| REDEMPTION_MEDIUM | +12.0 | doc§3.1 | — | — | 574, 582, 604, 605 |
| RELATED_PARTY_DISCLOSURE | +15.0 | doc§3.2 | — | 存在关联交易披露 | 30, 415 |
| CONCENTRATION_DISCLOSURE | +12.0 | doc§3.3 | — | 存在客户/供应商集中度披露 | 28, 29, 387 |
| PIPELINE_DISCLOSURE | +12.0 | doc§3.5 | — | 存在核心产品/管线进度披露 | 14, 16, 17, 20, 27 |

### 3.2 章节特征摘要

| 章节 | exists/skipped | 强度 | 关键字段 |
|------|----------------|------|----------|
| 3.1 | exists=True | high | — |
| 3.2 | exists=True | high | ratio_pct=5.0 |
| 3.3 | exists=True | high | — |
| 3.4 | exists=None | — | owner=finance |
| 3.5 | exists=True | high | — |
| 3.6 | exists=None | — | — |

### 3.3 召回证据明细

| 章节 | 页码 | 类型 | 置信度 | 摘录 |
|------|------|------|--------|------|
| 3.1 | 605 | text | 0.08 | 根據股東及貴公司就該等特別權利訂立的日期為2024年11月22日的終止協議，贖回權自首次遞交上市的首次上市申請表格日期的前一日起失效，而所有其他特別權利於上市後失效，惟(i)貴公司撤回其公開發售申請；(ii)聯交所、證券及期貨事務監察委員會（證監會）或任何主管證券監管機構決定不批准或拒絕貴公司的上市申請或以其他方式終止上市申請審核程序；或(iii)貴公司未能於2025年12月31日前完成公開發售， |
| 3.1 | 605 | text | 0.07 | 倘貴公司未能於2028年1月1日（「截止日期」）或之前完成合資格公開發售，則來自A、B及B+輪投資者的投資將有權但無責任透過向貴公司發出書面通知（「贖回通知」），要求貴公司贖回該優先股東持有的全部或部分當時已發行優先股（「贖回股份」）（每名該等提出請求的優先股股東，統稱「提出請求持有人」）。 |
| 3.1 | 574 | text | 0.07 | 儘管貴集團於2025年8月31日分別錄得流動負債淨額及資產淨值人民幣15,231,000元及人民幣144,791,000元，惟歷史財務資料乃按持續經營基準編製。於2025年8月31日，普通股贖回負債人民幣138,481,000元已入賬為流動負債，而其贖回權將於股份在聯交所完成首次上市前一日自動終止。貴公司董事認為，根據對貴集團預計現金流量的審閱，貴公司預期自2025年8月31日起未來十二個月內不會 |
| 3.1 | 582 | text | 0.07 | 對於附註24詳述的貴公司及貴公司附屬公司已發行的可贖回普通股，金融負債按贖回金額的攤銷成本確認並計入權益。有關期間的攤銷成本變動於損益確認。當與可贖回普通股相關的贖回權終止，則普通股贖回負債予以抵銷並計入權益。 |
| 3.1 | 604 | table | 0.07 | 2024年，揚子投資（香港）有限公司同意以總代價約人民幣10.65百萬元認購貴公司約人民幣0.78百萬元的註冊資本。翰思生物醫藥（香港）以總代價約人民幣10.65百萬元將其持有貴公司的0.87%的股權（註冊資本人民幣0.1百萬元）轉讓予海南揚子投資有限公司（「海南揚子」），此後，海南揚子與其他投資者擁有相同贖回權。 |
| 3.2 | 30 | text | 0.05 | 我們已與中美華世通生物醫藥科技訂立若干交易，該等交易於上市後將構成持續關連交易。有關我們與中美華世通生物醫藥科技的持續關連交易的進一步詳情，請參閱本招股章程「關連交易」一節。 |
| 3.2 | 415 | text | 0.04 | 於上市後，本集團成員公司與我們關連人士之間達成的若干交易將構成上市規則第十四A章項下的持續關連交易。 |
| 3.2 | 30 | text | 0.05 | 我們已與中美華世通生物醫藥科技訂立若干交易，該等交易於上市後將構成持續關連交易。有關我們與中美華世通生物醫藥科技的持續關連交易的進一步詳情，請參閱本招股章程「關連交易」一節。 |
| 3.2 | 415 | text | 0.04 | 於上市後，本集團成員公司與我們關連人士之間達成的若干交易將構成上市規則第十四A章項下的持續關連交易。 |
| 3.2 | 415 | text | 5.36 | 於上市後，本集團成員公司與我們關連人士之間達成的若干交易將構成上市規則第十四A章項下的持續關連交易。 |
| 3.3 | 28 | table | 0.07 | 截至2023年及2024年12月31日止年度及截至2025年8月31日止八個月，五大供應商應佔總採購額分別約為人民幣16.3百萬元、人民幣28.6百萬元及人民幣23.3百萬元，分別佔我們總採購額約51.8%、37.4%及45.5%。同期，單一最大供應商應佔採購額分別約為人民幣6.4百萬元、人民幣7.8百萬元及人民幣6.3百萬元，分別佔我們總採購額約20.4%、10.2%及12.4%。 |
| 3.3 | 28 | table | 0.07 | 截至2023年及2024年12月31日止年度及截至2025年8月31日止八個月，五大供應商應佔總採購額分別約為人民幣16.3百萬元、人民幣28.6百萬元及人民幣23.3百萬元，分別佔我們總採購額約51.8%、37.4%及45.5%。同期，單一最大供應商應佔採購額分別約為人民幣6.4百萬元、人民幣7.8百萬元及人民幣6.3百萬元，分別佔我們總採購額約20.4%、10.2%及12.4%。 |
| 3.3 | 387 | table | 2.37 | 截至2023年及2024年12月31日止年度及截至2025年8月31日止八個月，五大供應商應佔總採購額分別約為人民幣16.3百萬元、人民幣28.6百萬元及人民幣23.3百萬元，分別佔我們總採購額約51.8%、37.4%及45.5%。於該等期間，我們單一最大供應商應佔的採購額分別約為人民幣6.4百萬元、人民幣7.8百萬元及人民幣6.3百萬元，分別約佔我們採購總額的20.4%、10.2%及12.4%。 |
| 3.3 | 29 | table | 0.05 | 於往績記錄期間各期間，概無五大供應商為我們的關聯方。概無董事或其聯繫人或（據董事所知）任何擁有本公司股本5%以上的股東於截至2023年及2024年12月31日止年度以及截至2025年8月31日止八個月在任何五大供應商中擁有任何權益。 |
| 3.3 | 29 | table | 0.05 | 於往績記錄期間各期間，概無五大供應商為我們的關聯方。概無董事或其聯繫人或（據董事所知）任何擁有本公司股本5%以上的股東於截至2023年及2024年12月31日止年度以及截至2025年8月31日止八個月在任何五大供應商中擁有任何權益。 |
| 3.5 | 16 | text | 0.07 | 除HX301乃自Onconova Therapeutics, Inc.授權引進外，我們的管線候選產品全部由我們自主研發。我們構建產品管線，旨在利用先天及適應性免疫實現潛在協同效應。我們的產品管線旨在解決現有檢查點抑制劑免疫療法的局限性，包括免疫抑制性腫瘤微環境致使「冷腫瘤」響應有限以及其他未獲滿足的醫療需求，從而為各種癌症患者及其他疾病適應症患者帶來臨床裨益。截至最後實際可行日期，我們已建立由10 |
| 3.5 | 17 | text | 0.07 | 我們根據相關方案及批准進行HX009的臨床研究。於2024年9月，我們的中國法律顧問連同獨家保薦人及其法律顧問在北京與國家藥監局藥審中心臨床試驗管理辦公室的審查員進行了面對面訪談，期間已確認（其中包括）我們已完成一項常規I期臨床研究，且HX009的國家藥監局一次性傘式批准允許本公司在III期研究之前進行HX009-I-01中國研究下的臨床研究，而無需再次獲得國家藥監局的監管批准。有關詳情請參閱本招 |
| 3.5 | 20 | text | 0.05 | 我們的核心產品HX009是一種同時靶向CD47及PD-1的雙特異性抗體融合蛋白。根據弗若斯特沙利文報告，截至最後實際可行日期，HX009的臨床試驗進展在同類CD47靶向雙特異性抗體／雙功能融合蛋白產品中處於全球領先地位。 |
| 3.5 | 27 | text | 0.05 | 我們的研發團隊通常負責核心產品及其他管線產品的全球開發。我們的研發團隊有能力在中國及其他司法權區同時開展不同開發階段的臨床項目。彼等平均擁有10年左右的行業工作經驗，且幾乎全部擁有本科或以上學歷。就自主發現及開發的候選藥物而言，我們與臨床開發團隊共同開展藥物發現、質量保證及臨床活動，其中包括：(i)協調所有臨床開發工作；(ii)制定臨床試驗的關鍵要素；(iii)安排及協調合適的CRO參與臨床試驗， |
| 3.5 | 14 | text | 0.05 | 截至最後實際可行日期，我們已開發十種候選藥物組成的管線，包括我們的核心產品HX009及兩種主要產品HX044及HX301，其中有八種針對腫瘤科的候選藥物及兩種針對自身免疫疾病的候選藥物。截至最後實際可行日期，我們的核心產品以及主要產品分別在中國及澳大利亞進行臨床試驗。下圖概述截至最後實際可行日期我們管線產品的開發狀態。 |

### 3.4 计分证据（score_breakdown）

#### `REDEMPTION_MEDIUM`（+12.0，doc§3.1）

- p605（text）：根據股東及貴公司就該等特別權利訂立的日期為2024年11月22日的終止協議，贖回權自首次遞交上市的首次上市申請表格日期的前一日起失效，而所有其他特別權利於上市後失效，惟(i)貴公司撤回其公開發售申請；(ii)聯交所、證券及期貨事務監察委員會（證監會）或任何主管證券監管機構決定不批准或拒絕貴公司的上市申請或以其他方式終止上市申請審核程序；或(iii)貴公司未能於2025年12月31日前完成公開發售，
- p605（text）：倘貴公司未能於2028年1月1日（「截止日期」）或之前完成合資格公開發售，則來自A、B及B+輪投資者的投資將有權但無責任透過向貴公司發出書面通知（「贖回通知」），要求貴公司贖回該優先股東持有的全部或部分當時已發行優先股（「贖回股份」）（每名該等提出請求的優先股股東，統稱「提出請求持有人」）。
- p574（text）：儘管貴集團於2025年8月31日分別錄得流動負債淨額及資產淨值人民幣15,231,000元及人民幣144,791,000元，惟歷史財務資料乃按持續經營基準編製。於2025年8月31日，普通股贖回負債人民幣138,481,000元已入賬為流動負債，而其贖回權將於股份在聯交所完成首次上市前一日自動終止。貴公司董事認為，根據對貴集團預計現金流量的審閱，貴公司預期自2025年8月31日起未來十二個月內不會
- p582（text）：對於附註24詳述的貴公司及貴公司附屬公司已發行的可贖回普通股，金融負債按贖回金額的攤銷成本確認並計入權益。有關期間的攤銷成本變動於損益確認。當與可贖回普通股相關的贖回權終止，則普通股贖回負債予以抵銷並計入權益。
- p604（table）：2024年，揚子投資（香港）有限公司同意以總代價約人民幣10.65百萬元認購貴公司約人民幣0.78百萬元的註冊資本。翰思生物醫藥（香港）以總代價約人民幣10.65百萬元將其持有貴公司的0.87%的股權（註冊資本人民幣0.1百萬元）轉讓予海南揚子投資有限公司（「海南揚子」），此後，海南揚子與其他投資者擁有相同贖回權。

#### `RELATED_PARTY_DISCLOSURE`（+15.0，doc§3.2）

存在关联交易披露

- p30（text）：我們已與中美華世通生物醫藥科技訂立若干交易，該等交易於上市後將構成持續關連交易。有關我們與中美華世通生物醫藥科技的持續關連交易的進一步詳情，請參閱本招股章程「關連交易」一節。
- p415（text）：於上市後，本集團成員公司與我們關連人士之間達成的若干交易將構成上市規則第十四A章項下的持續關連交易。
- p30（text）：我們已與中美華世通生物醫藥科技訂立若干交易，該等交易於上市後將構成持續關連交易。有關我們與中美華世通生物醫藥科技的持續關連交易的進一步詳情，請參閱本招股章程「關連交易」一節。
- p415（text）：於上市後，本集團成員公司與我們關連人士之間達成的若干交易將構成上市規則第十四A章項下的持續關連交易。
- p415（text）：於上市後，本集團成員公司與我們關連人士之間達成的若干交易將構成上市規則第十四A章項下的持續關連交易。

#### `CONCENTRATION_DISCLOSURE`（+12.0，doc§3.3）

存在客户/供应商集中度披露

- p28（table）：截至2023年及2024年12月31日止年度及截至2025年8月31日止八個月，五大供應商應佔總採購額分別約為人民幣16.3百萬元、人民幣28.6百萬元及人民幣23.3百萬元，分別佔我們總採購額約51.8%、37.4%及45.5%。同期，單一最大供應商應佔採購額分別約為人民幣6.4百萬元、人民幣7.8百萬元及人民幣6.3百萬元，分別佔我們總採購額約20.4%、10.2%及12.4%。
- p28（table）：截至2023年及2024年12月31日止年度及截至2025年8月31日止八個月，五大供應商應佔總採購額分別約為人民幣16.3百萬元、人民幣28.6百萬元及人民幣23.3百萬元，分別佔我們總採購額約51.8%、37.4%及45.5%。同期，單一最大供應商應佔採購額分別約為人民幣6.4百萬元、人民幣7.8百萬元及人民幣6.3百萬元，分別佔我們總採購額約20.4%、10.2%及12.4%。
- p387（table）：截至2023年及2024年12月31日止年度及截至2025年8月31日止八個月，五大供應商應佔總採購額分別約為人民幣16.3百萬元、人民幣28.6百萬元及人民幣23.3百萬元，分別佔我們總採購額約51.8%、37.4%及45.5%。於該等期間，我們單一最大供應商應佔的採購額分別約為人民幣6.4百萬元、人民幣7.8百萬元及人民幣6.3百萬元，分別約佔我們採購總額的20.4%、10.2%及12.4%。
- p29（table）：於往績記錄期間各期間，概無五大供應商為我們的關聯方。概無董事或其聯繫人或（據董事所知）任何擁有本公司股本5%以上的股東於截至2023年及2024年12月31日止年度以及截至2025年8月31日止八個月在任何五大供應商中擁有任何權益。
- p29（table）：於往績記錄期間各期間，概無五大供應商為我們的關聯方。概無董事或其聯繫人或（據董事所知）任何擁有本公司股本5%以上的股東於截至2023年及2024年12月31日止年度以及截至2025年8月31日止八個月在任何五大供應商中擁有任何權益。

#### `PIPELINE_DISCLOSURE`（+12.0，doc§3.5）

存在核心产品/管线进度披露

- p16（text）：除HX301乃自Onconova Therapeutics, Inc.授權引進外，我們的管線候選產品全部由我們自主研發。我們構建產品管線，旨在利用先天及適應性免疫實現潛在協同效應。我們的產品管線旨在解決現有檢查點抑制劑免疫療法的局限性，包括免疫抑制性腫瘤微環境致使「冷腫瘤」響應有限以及其他未獲滿足的醫療需求，從而為各種癌症患者及其他疾病適應症患者帶來臨床裨益。截至最後實際可行日期，我們已建立由10
- p17（text）：我們根據相關方案及批准進行HX009的臨床研究。於2024年9月，我們的中國法律顧問連同獨家保薦人及其法律顧問在北京與國家藥監局藥審中心臨床試驗管理辦公室的審查員進行了面對面訪談，期間已確認（其中包括）我們已完成一項常規I期臨床研究，且HX009的國家藥監局一次性傘式批准允許本公司在III期研究之前進行HX009-I-01中國研究下的臨床研究，而無需再次獲得國家藥監局的監管批准。有關詳情請參閱本招
- p20（text）：我們的核心產品HX009是一種同時靶向CD47及PD-1的雙特異性抗體融合蛋白。根據弗若斯特沙利文報告，截至最後實際可行日期，HX009的臨床試驗進展在同類CD47靶向雙特異性抗體／雙功能融合蛋白產品中處於全球領先地位。
- p27（text）：我們的研發團隊通常負責核心產品及其他管線產品的全球開發。我們的研發團隊有能力在中國及其他司法權區同時開展不同開發階段的臨床項目。彼等平均擁有10年左右的行業工作經驗，且幾乎全部擁有本科或以上學歷。就自主發現及開發的候選藥物而言，我們與臨床開發團隊共同開展藥物發現、質量保證及臨床活動，其中包括：(i)協調所有臨床開發工作；(ii)制定臨床試驗的關鍵要素；(iii)安排及協調合適的CRO參與臨床試驗，
- p14（text）：截至最後實際可行日期，我們已開發十種候選藥物組成的管線，包括我們的核心產品HX009及兩種主要產品HX044及HX301，其中有八種針對腫瘤科的候選藥物及兩種針對自身免疫疾病的候選藥物。截至最後實際可行日期，我們的核心產品以及主要產品分別在中國及澳大利亞進行臨床試驗。下圖概述截至最後實際可行日期我們管線產品的開發狀態。

### 3.5 工具调用链

- 耗时：`3.158s`

1. **`retrieve_legal`**
   ```json
   {"source": "offline:/nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_legal.json", "fields": ["REDEMPTION_CLAUSE", "RELATED_PARTY", "CONCENTRATION", "CASH_BURN_PRESSURE", "PIPELINE_RISK", "PRE_IPO_VALUATION"], "per_query": 6, "has_evidence_by_field": true, "hint": null}
   ```
2. **`parse_grep`**
   ```json
   {"path": "/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/03378_15-12-2025_翰思艾泰－Ｂ_全球發售/full_parse.json", "hits": 0, "pages": []}
   ```
3. **`retrieve_section_evidence`**
   ```json
   {"intents": {"redemption": {"hits": 3, "pages": [262, 271, 80], "route": [{"section_id": "history_and_corporate_structure", "section_title": "歷史、發展及公司架構", "start_page": 241, "end_page": 276, "confidence": 0.95}, {"section_id": "risk_factors", "section_title": "風險因素", "start_page": 73, "end_page": 126, "confidence": 0.95}]}, "related_party": {"hits": 8, "pages": [415, 415, 416, 425, 425, 424, 425, 424], "route": [{"section_id": "connected_transactions", "section_title": "關連交易", "start_page": 415, "end_page": 425, "confidence": 0.95}, {"section_id": "business", "section_title": "業務", "start_page": 277, "end_page": 414, "confidence": 0.95}, {"section_id": "financial_information", "section_title": "財務資料", "start_page": 474, "end_page": 507, "confidence": 0.95}]}, "concentration": {"hits": 1, "pages": [387], "route": [{"section_id": "business", "section_title": "業務", "start_page": 277, "end_page": 414, "confidence": 0.95}, {"section_id": "risk_factors", "section_title": "風險因素", "start_page": 73, "end_page": 126, "confidence": 0.95}, {"section_id": "financial_information", "section_title": "財務資料", "start_page": 474, "end_page": 507, "confidence": 0.95}]}}}
   ```
4. **`extract_legal`**
   ```json
   {"sections": {"3.1": {"exists": true, "skipped": null, "evidence_n": 5, "search_log": {"keywords_tried": ["赎回", "贖回", "对赌", "對賭", "回购", "回購", "优先股", "優先股", "领售", "領售", "撤资", "撤資", "贖回權", "可換股", "可转换可赎回", "可轉換可贖回", "股东协议", "股東協議", "特别权利", "特別權利", "赎回权终止", "特別權利終止"], "pages_scanned": [80, 262, 271, 574, 582, 604, 605], "raw_hits": 13, "filtered_noise": 0, "strong_hits": 13, "note": "命中对赌/赎回相关披露"}, "top1_supplier_pct": null, "top5_supplier_pct": null}, "3.2": {"exists": true, "skipped": null, "evidence_n": 5, "search_log": null, "top1_supplier_pct": null, "top5_supplier_pct": null}, "3.3": {"exists": true, "skipped": null, "evidence_n": 5, "search_log": null, "top1_supplier_pct": 20.4, "top5_supplier_pct": 20.4}, "3.5": {"exists": true, "skipped": false, "evidence_n": 5, "search_log": {"raw_hits": 10, "strong_hits": 10, "high_hits": 0, "pages_scanned": [14, 16, 17, 20, 27]}, "top1_supplier_pct": null, "top5_supplier_pct": null}}}
   ```
5. **`score_legal`**
   ```json
   {"risk_score": 51.0, "breakdown_n": 4}
   ```

### 3.6 分析结论

- 风险分 **51.0**（medium）。打分来自披露基础分或规则命中（见 score_breakdown）。
- 3.1 对赌/赎回：exists=`True`，证据强度=`high`
- 3.2 关联交易：exists=`True`，占比=`5.0`。
- 3.3 集中度：exists=`True`，证据页=[28, 28, 387, 29, 29]。

## 4. 改进建议

1. **[已做] 财务 LLM 主路径**：retrieve → extract_metrics → gates → analyze_finance(单次四维 LLM) → 可解释评分；规则打分降为 fallback（`--finance-rules-only`）。
2. **[已做] Gemma4 reasoning**：OpenRouter `reasoning.enabled`；日志区分 `[model_think]` / `[structured_reasoning]`。
3. **[已做] 推理日志落盘**：`logs/{doc}_{agent}_{ts}.log` + `.jsonl`（时间/文档/流程/工具skills/过程/结果/推理链）。
4. **[已做] 财务 BS 交叉校验**：若 TOTAL_ASSETS < NET_ASSETS，用 NET+LIAB 回填。
5. **法务检索源**：可用 `--use-live-retrieval`；`--use-llm` 做法务结构化增强。

---

_本报告由 `scripts/generate_analysis_report.py` 根据 Agent 结构化输出自动生成。_
