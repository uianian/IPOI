# 伊登軟件 — 财务/法务 Agent 结果分析报告

- 生成时间：2026-07-26 18:04:21
- 招股书：`01147_23-04-2020_伊登軟件_股份發售.pdf`
- doc_id：`eden`
- 参考基本面融合分：`11.25` （legal×0.45 + finance×0.55；总控未启用）
- 财务评分模式：`react+rules_floor`
- 推理日志：`/nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/logs/伊登軟件_finance_20260726_180352.log`
- 说明：reference_fundamental_score = legal*0.45 + finance*0.55; master/cross_agent_features 为本轮占位，总控辩论未启用

## 1. 总览

| Agent | 风险分 (0-100↑风险) | 等级 | 摘要 |
|-------|---------------------|------|------|
| 财务穿透 | **0.0** | very_low | 财务状况健康，持续盈利且现金流稳健，但毛利率较低，呈现典型的软件分销/集成特征。 |
| 法务合规 | **25.0** | low | 法务 3.1/3.2/3.3 抽取完成；3.5=跳过；风险分 25.0 (low) |

## 2. 财务穿透 Agent

### 2.1 得分与分解

_无扣分项（未触发风险规则，或证据不足未计分）_

### 2.2 四维分析（LLM）

#### `profitability_growth` — status=`analyzed`

公司营收规模稳步增长（2016年32.7万至2019年79.2万），且连续四年实现净利润，盈利能力稳定。


#### `cash_flow` — status=`analyzed`

除2016年微幅负值外，CFO持续为正且与净利润匹配，现金流质量较高。


#### `solvency` — status=`analyzed`

净资产从28k增长至96k，资产负债结构健康，无明显偿债风险。


#### `business_context` — status=`analyzed`

毛利率维持在10.5%-12.5%的较低水平，显著低于纯软件开发行业，结合证据显示其涉及办公软件供应，具有典型的软件分销或系统集成业务特征。



### 2.3 推理链

**[structured_reasoning]**

发行人财务表现稳健，连续四年盈利且经营性现金流充足。虽然毛利率较低，但符合其分销/集成业务模式，无重大财务风险点。

**[model_think 摘录]**（全文见 logs）

> The user wants a financial risk penetration analysis for "Eden Software" (伊登軟件).      *   `REV`: Growing steadily (327k -> 791k).     *   `GP`: Positive and growing (37k -> 83k).     *   `GP_MARGIN`: Low for a software company (10.5% - 12.5%).     *   `NET_PROFIT`: Consistently profitable (12k -> 24k).     *   `CFO`: Mostly positive (except 2016), showing good cash generation.     *   `CASH_EQ`: Stable/Growing (23.8k in 2019).     *   `NET_ASSETS`: Growing (28k -> 96k).     *   `is_unprofitable`

### 2.4 门控

```json
{
  "is_unprofitable": false,
  "latest_full_year_loss": false,
  "continuous_net_loss": false,
  "profitability_known": true,
  "profitability_status": "profitable",
  "profitability_basis": "NET_LOSS/年內利潤 series; positive=profit",
  "issuer_type": "general",
  "is_biotech_18a": false,
  "skip_3_4": true,
  "skip_3_4_reason": "profitable",
  "skip_2_4": true,
  "skip_2_4_reason": "non-biotech",
  "skip_3_5": true,
  "skip_3_5_reason": "non-biotech"
}
```

### 2.5 抽取指标

| 指标 | 2016 | 2017 | 2018 | 2019 |
|------|------|------|------|------|
| REV | 327,293 | 468,439 | 612,092 | 791,888 |
| OTHER_INCOME | 2,127 | 2,217 | 2,547 | 3,886 |
| COGS | -289,437 | -409,980 | -535,548 | -708,686 |
| GP | 37,856 | 58,459 | 76,544 | 83,202 |
| RD_EXP | -3,824 | -10,589 | -18,482 | -19,279 |
| SGA | -9,909 | -10,464 | -11,150 | -13,886 |
| NET_LOSS | 12,011 | 22,273 | 27,130 | 24,548 |
| NET_ASSETS | 28,010 | 44,209 | 65,158 | 96,261 |
| CASH_EQ | 43,429 | 13,997 | 14,022 | 23,892 |
| TOTAL_ASSETS | 183,618 | 136,705 | 189,132 | 206,500 |
| CFO | -902.00 | 21,777 | 12,594 | 10,071 |
| CFF | 29,995 | -54,769 | -13,479 | 2,366 |
| END_CASH | 43,429 | 13,997 | 14,022 | 23,892 |
| GP_MARGIN | 11.57 | 12.48 | 12.51 | 10.51 |

3.4 现金消耗：skipped=`True`，reason=`profitable`，runway=`None`

### 2.6 召回证据（主表）

| 表/字段 | 页码 | 类型 | 命中数 | 年份列 | 摘录 |
|--------|------|------|--------|--------|------|
| TBL_IS | 327 | table | — | — | 截至12月31日止年度 附註 2016年人民幣千元 2017年人民幣千元 2018年人民幣千元 2019年人民幣千元 收益 8 327,293 468,439 612,092 791,888 銷售成本 (289,437) (409,980) (535,548) (708,686) 毛利 37,856 58,459 76,544 83,202 其他收入及收益 8 2,127 2,217 2,547… |
| TBL_BS | 328 | table | — | — | 於12月31日 附註 2016年人民幣千元 2017年人民幣千元 2018年人民幣千元 2019年人民幣千元 非流動資產 物業、廠房及設備 16 1,521 1,021 689 1,369 使用權資產 17 8,287 6,607 11,181 8,083 於一間聯營公司的投資 18 – 1,500 1,500 1,128 遞延稅項資產 29 114 110 112 239 非流動資產總值 9,… |
| TBL_CF | 330 | table | — | — | 截至12月31日止年度 附註 2016年人民幣千元 2017年人民幣千元 2018年人民幣千元 2019年人民幣千元 經營活動所得現金流量 除税前溢利 13,797 26,005 31,655 28,874 就下列各項作出調整： 物業、廠房及設備折舊 16 556 511 393 495 使用權資產折舊 17 1,538 1,533 1,287 3,327 按公允價值計入損益的 金融資產收益 8… |
| TBL_BS_COMPANY | 332 | table | — | — | 附註 2018年12月31日人民幣千元 2019年12月31日人民幣千元 非流動資產 於一間附屬公司的投資 –* –* 非流動資產總值 –* –* 流動資產 預付款項、按金及其他應收款項 1,379 3,261 現金及現金等價物 2,111 3,177 流動資產總值 3,490 6,438 流動負債 其他應付款項及應計費用 190 1,465 流動負債總額 190 1,465 流動資產淨值 3,… |

#### 2.6.1 章节化上下文证据

- intent=`business_model` query=`公司主要业务模式、收入构成、毛利率较低的原因` → business@p112-207, risk_factors@p44-71, summary@p8-27

| 意图章节 | 页码 | 类型 | 分数 | 匹配词 | 摘录 |
|---|---:|---|---:|---|---|
| business | 141 | text | 1.551 | — | 我們的業務分部及模式 |
| business | 142 | text | 1.5507 | — | 我們的業務模式 |
| summary | 9 | text | 1.5504 | — | 業務模式 |
| business | 165 | text | 1.4086 | — | 根據行業報告，客戶A的營運及管理高度依賴於供應商A的辦公相關軟件的可靠性及性能。供應商A的任何辦公相關軟件的性能故障或缺陷將影響客戶A整體或部分的業務營運及管理，可能對彼等造成嚴重損失及業務中斷。此外，我們在向客戶A穩定供應供應商A的各類辦公相關軟件及提供售後服務（例如就購自本集團的IT產品提供技術及維護支持）方面擁有良好往績記錄。據弗若斯特沙利文告知，供應商A採用委聘地方授權服務提供商或戰略地方合作夥伴向中國的終端客戶銷售及／或分銷其產品及服務的銷售模式。根據該銷售模式，供 |
| business | 202 | table | 1.3948 | — | <table><tr><td>獎項／資格</td><td>頒發機構</td><td>頒發年份／期間</td></tr><tr><td>2017年度深圳市軟件業務收入前百家企業</td><td>深圳市軟件行業協會</td><td>2018年5月</td></tr><tr><td>ISO9001:2015(軟件開發及技術諮詢服務、雲業務)</td><td>深圳市環通認證中心有限公司</td><td>2017年6月</td></tr><tr><td>2016中國年度最佳僱主提名獎< |

### 2.7 工具调用链

- 耗时：`28.892s`

1. **`retrieve_finance`**
   ```json
   {"turn": 1, "arguments": {"reason": "开始财务穿透分析，首先需要检索三张财务主表以获取基础数据。"}, "observation": {"ok": true, "source": "offline:/nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_eden_finance.json", "tables": ["TBL_IS", "TBL_BS", "TBL_BS_COMPANY", "TBL_CF"], "skipped_fields": 8, "hint": "下一步可调用 extract_metrics"}, "duration_ms": 5247}
   ```
2. **`extract_metrics`**
   ```json
   {"turn": 2, "arguments": {"reason": "从检索到的财务主表中抽取标准指标，用于后续的门控计算和风险评估。"}, "observation": {"ok": true, "metric_keys": ["REV", "OTHER_INCOME", "COGS", "GP", "RD_EXP", "SGA", "NET_LOSS", "NET_ASSETS", "CASH_EQ", "TOTAL_ASSETS", "CFO", "CFF", "END_CASH", "GP_MARGIN"], "years": ["2016", "2017", "2018", "2019"], "metrics_summary": {"REV": {"2016": 327293.0, "2017": 468439.0, "2018": 612092.0, "2019": 791888.0}, "OTHER_INCOME": {"2016": 2127.0, "2017": 2217.0, "2018": 2547.0, "2019": 3886.0}, "GP": {"2016": 37856.0, "2017": 58459.0, "2018": 76544.0, "2019": 83202.0}, "GP_MARGIN": {"2016": 11.57, "2017": 12.48, "2018": 12.51, "2019": 10.51}, "NET_PROFIT_OR_LOSS": {"2016": 12011.0, "2017": 22273.0, "2018": 27130.0, "2019": 24548.0}, "CFO": {"2016": -902.0, "2017": 21777.0, "2018": 12594.0, "2019": 10071.0}, "CASH_EQ": {"2016": 43429.0, "2017": 13997.0, "2018": 14022.0, "2019": 23892.0}, "END_CASH": {"2016": 43429.0, "2017": 13997.0, "2018": 14022.0, "2019": 23892.0}, "TOTAL_ASSETS": {"2016": 183618.0, "2017": 136705.0, "2018": 189132.0, "2019": 206500.0}, "NET_ASSETS": {"2016": 28010.0, "2017": 44209.0, "2018": 65158.0, "2019": 96261.0}}, "metric_note": "NET_PROFIT_OR_LOSS 为底线利润/亏损字段；正数=盈利，负数=亏损。", "bs_reconcile": {"changed": false, "note": null}, "hint": "下一步可调用 derive_gates"}, "duration_ms": 946}
   ```
3. **`derive_gates`**
   ```json
   {"turn": 3, "arguments": {"reason": "根据提取的指标计算盈利状态和门控，决定是否需要计算现金跑道。"}, "observation": {"ok": true, "gates": {"is_unprofitable": false, "continuous_net_loss": false, "latest_full_year_loss": false, "skip_3_4": true, "skip_3_4_reason": "profitable", "skip_2_4": true, "issuer_type": "general", "is_biotech_18a": false, "net_series": {"2016": 12011.0, "2017": 22273.0, "2018": 27130.0, "2019": 24548.0}, "profitability_basis": "NET_LOSS/年內利潤 series; positive=profit", "profitability_known": true, "profitability_status": "profitable"}, "fast_path": {"eligible": false, "reason": null}, "hint": "若未盈利可 calc_cash_runway；非主表主题可 retrieve_context_evidence；否则 submit"}, "duration_ms": 1919}
   ```
4. **`retrieve_context_evidence`**
   ```json
   {"turn": 4, "arguments": {"intent": "business_model", "query": "公司主要业务模式、收入构成、毛利率较低的原因", "reason": "软件公司毛利率仅10%-12%，低于行业常规水平，需确认其业务模式（如是否包含大量硬件销售或集成服务）。"}, "observation": {"ok": true, "doc_id": "eden", "intent": "business_model", "query": "公司主要业务模式、收入构成、毛利率较低的原因", "n": 5, "route": [{"section_id": "business", "section_title": "業務", "start_page": 112, "end_page": 207, "confidence": 0.95}, {"section_id": "risk_factors", "section_title": "風險因素", "start_page": 44, "end_page": 71, "confidence": 0.95}, {"section_id": "summary", "section_title": "概要", "start_page": 8, "end_page": 27, "confidence": 0.95}], "hits": [{"page": 141, "section_id": "business", "source_type": "text", "score": 1.551, "matched_terms": [], "excerpt": "我們的業務分部及模式"}, {"page": 142, "section_id": "business", "source_type": "text", "score": 1.5507, "matched_terms": [], "excerpt": "我們的業務模式"}, {"page": 9, "section_id": "summary", "source_type": "text", "score": 1.5504, "matched_terms": [], "excerpt": "業務模式"}, {"page": 165, "section_id": "business", "source_type": "text", "score": 1.4086, "matched_terms": [], "excerpt": "根據行業報告，客戶A的營運及管理高度依賴於供應商A的辦公相關軟件的可靠性及性能。供應商A的任何辦公相關軟件的性能故障或缺陷將影響客戶A整體或部分的業務營運及管理，可能對彼等造成嚴重損失及業務中斷。此外，我們在向客戶A穩定供應供應商A的各類辦"}, {"page": 202, "section_id": "business", "source_type": "table", "score": 1.3948, "matched_terms": [], "excerpt": "<table><tr><td>獎項／資格</td><td>頒發機構</td><td>頒發年份／期間</td></tr><tr><td>2017年度深圳市軟件業務收入前百家企業</td><td>深圳市軟件行業協會</td><td>2018年5"}], "hint": "完整证据已保存到 state；submit 时引用 page/section/excerpt 即可"}, "duration_ms": 6477}
   ```
5. **`submit_finance_report`**
   ```json
   {"turn": 5, "arguments": {"dimensions": [{"analysis": "公司营收规模稳步增长（2016年32.7万至2019年79.2万），且连续四年实现净利润，盈利能力稳定。", "dimension": "profitability_growth"}, {"analysis": "除2016年微幅负值外，CFO持续为正且与净利润匹配，现金流质量较高。", "dimension": "cash_flow"}, {"analysis": "净资产从28k增长至96k，资产负债结构健康，无明显偿债风险。", "dimension": "solvency"}, {"analysis": "毛利率维持在10.5%-12.5%的较低水平，显著低于纯软件开发行业，结合证据显示其涉及办公软件供应，具有典型的软件分销或系统集成业务特征。", "dimension": "business_context"}], "negative_findings": [], "reasoning": "发行人财务表现稳健，连续四年盈利且经营性现金流充足。虽然毛利率较低，但符合其分销/集成业务模式，无重大财务风险点。", "risk_level": "very_low", "risk_points": [], "risk_score": 0, "score_breakdown": [], "summary": "财务状况健康，持续盈利且现金流稳健，但毛利率较低，呈现典型的软件分销/集成特征。"}, "observation": {"ok": true, "finished": true, "risk_score": 0.0, "risk_level": "very_low", "warnings": [], "summary": "财务状况健康，持续盈利且现金流稳健，但毛利率较低，呈现典型的软件分销/集成特征。", "rules_floor": {"rules_score": 0.0, "rules_score_deduped": 0, "llm_score": 0.0, "final_score": 0.0, "flags": {"continuous_net_loss": false, "latest_full_year_loss": false, "cfo_persistently_negative": false, "gp_margin_drop_gt_5pp": false, "runway_lt_12": false, "runway_12_24": false, "burn_yoy_up_gt_30": false}}}, "duration_ms": 13280}
   ```

### 2.8 分析结论

- 评分模式 **react+rules_floor**；风险分 **0.0**（very_low）。门控：未盈利=`False`，跳过3.4=`True`（profitable），跳过2.4=`True`（non-biotech）。
- 模型 think 状态：`ok`（全文见推理日志 `[model_think]`）。
- 结构化推理摘要：发行人财务表现稳健，连续四年盈利且经营性现金流充足。虽然毛利率较低，但符合其分销/集成业务模式，无重大财务风险点。
- LLM 摘要：财务状况健康，持续盈利且现金流稳健，但毛利率较低，呈现典型的软件分销/集成特征。
- 期内利润（NET_LOSS 字段存利润序列，正数=盈利）：2016=12,011、2017=22,273、2018=27,130、2019=24,548。
- 收入与毛利率：2016–2019 收入 327,293→791,888（千元），毛利率 11.57%→10.51%。
- 主表证据定位：TBL_IS@p327, TBL_BS@p328, TBL_CF@p330, TBL_BS_COMPANY@p332。
- 推理日志：`/nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/logs/伊登軟件_finance_20260726_180352.log`

## 3. 法务合规 Agent

### 3.1 得分与分解

| 代码 | 加分 | 规则 | 指标值 | 说明 | 证据页 |
|------|------|------|--------|------|--------|
| CONCENTRATION_HIGH | +25.0 | doc§3.3 | — | — | 11, 15, 16 |

### 3.2 章节特征摘要

| 章节 | exists/skipped | 强度 | 关键字段 |
|------|----------------|------|----------|
| 3.1 | exists=False | low | — |
| 3.2 | exists=False | low | — |
| 3.3 | exists=True | high | top1_customer_pct=49.6; top5_customer_pct=63.1 |
| 3.4 | exists=None | — | owner=finance |
| 3.5 | skipped=True | — | reason=non-biotech |
| 3.6 | exists=None | — | — |

### 3.3 召回证据明细

| 章节 | 页码 | 类型 | 置信度 | 摘录 |
|------|------|------|--------|------|
| 3.1 | — | — | — | 未召回强证据 / 判定不存在 |
| 3.2 | — | — | — | 未召回强证据 / 判定不存在 |
| 3.3 | 15 | table | 0.07 | 於截至2019年12月31日止四個年度，向五大供應商作出的採購總額分別佔我們採購總額的約42.9%、60.0%、62.6%及62.3%，向最大供應商（供應商A）作出的採購額佔我們同期採購總額的約29.7%、37.2%、36.4%及32.7%。截至2019年12月31日止四個年度，分包成本佔我們銷售成本總額約6.5%、5.5%、8.1%及5.4%。 |
| 3.3 | 15 | table | 0.07 | 於截至2019年12月31日止四個年度，向五大供應商作出的採購總額分別佔我們採購總額的約42.9%、60.0%、62.6%及62.3%，向最大供應商（供應商A）作出的採購額佔我們同期採購總額的約29.7%、37.2%、36.4%及32.7%。截至2019年12月31日止四個年度，分包成本佔我們銷售成本總額約6.5%、5.5%、8.1%及5.4%。 |
| 3.3 | 16 | table | 0.05 | 於往績記錄期，我們主要基於供應商A的產品及服務向客戶提供IT服務及主要通過供應商A購買供應商A的產品及服務。截至2019年12月31日止四個年度，我們來自供應商A的產品及服務的收益（包括向供應商A直接購買及向其授權分銷商或經銷商購買）分別約為人民幣137.7百萬元、人民幣285.0百萬元、人民幣410.0百萬元及人民幣548.8百萬元，分別約佔我們同期總收益的41.9%、60.8%、67.0%及6 |
| 3.3 | 16 | table | 0.05 | 於往績記錄期，我們主要基於供應商A的產品及服務向客戶提供IT服務及主要通過供應商A購買供應商A的產品及服務。截至2019年12月31日止四個年度，我們來自供應商A的產品及服務的收益（包括向供應商A直接購買及向其授權分銷商或經銷商購買）分別約為人民幣137.7百萬元、人民幣285.0百萬元、人民幣410.0百萬元及人民幣548.8百萬元，分別約佔我們同期總收益的41.9%、60.8%、67.0%及6 |
| 3.3 | 11 | table | 0.07 | 截至2019年12月31日止四個年度，來自我們五大客戶的收益分別佔我們總收益約57.3%、63.1%、59.4%及58.7%。其間，截至2019年12月31日止四個年度，來自我們最大客戶的收益分別佔我們總收益約42.8%、49.6%、42.3%及40.4%。 |
| 3.5 | — | — | — | （已跳过：non-biotech） |

### 3.4 计分证据（score_breakdown）

#### `CONCENTRATION_HIGH`（+25.0，doc§3.3）

- p15（table）：於截至2019年12月31日止四個年度，向五大供應商作出的採購總額分別佔我們採購總額的約42.9%、60.0%、62.6%及62.3%，向最大供應商（供應商A）作出的採購額佔我們同期採購總額的約29.7%、37.2%、36.4%及32.7%。截至2019年12月31日止四個年度，分包成本佔我們銷售成本總額約6.5%、5.5%、8.1%及5.4%。
- p15（table）：於截至2019年12月31日止四個年度，向五大供應商作出的採購總額分別佔我們採購總額的約42.9%、60.0%、62.6%及62.3%，向最大供應商（供應商A）作出的採購額佔我們同期採購總額的約29.7%、37.2%、36.4%及32.7%。截至2019年12月31日止四個年度，分包成本佔我們銷售成本總額約6.5%、5.5%、8.1%及5.4%。
- p16（table）：於往績記錄期，我們主要基於供應商A的產品及服務向客戶提供IT服務及主要通過供應商A購買供應商A的產品及服務。截至2019年12月31日止四個年度，我們來自供應商A的產品及服務的收益（包括向供應商A直接購買及向其授權分銷商或經銷商購買）分別約為人民幣137.7百萬元、人民幣285.0百萬元、人民幣410.0百萬元及人民幣548.8百萬元，分別約佔我們同期總收益的41.9%、60.8%、67.0%及6
- p16（table）：於往績記錄期，我們主要基於供應商A的產品及服務向客戶提供IT服務及主要通過供應商A購買供應商A的產品及服務。截至2019年12月31日止四個年度，我們來自供應商A的產品及服務的收益（包括向供應商A直接購買及向其授權分銷商或經銷商購買）分別約為人民幣137.7百萬元、人民幣285.0百萬元、人民幣410.0百萬元及人民幣548.8百萬元，分別約佔我們同期總收益的41.9%、60.8%、67.0%及6
- p11（table）：截至2019年12月31日止四個年度，來自我們五大客戶的收益分別佔我們總收益約57.3%、63.1%、59.4%及58.7%。其間，截至2019年12月31日止四個年度，來自我們最大客戶的收益分別佔我們總收益約42.8%、49.6%、42.3%及40.4%。

### 3.5 工具调用链

- 耗时：`2.79s`

1. **`retrieve_legal`**
   ```json
   {"source": "offline:/nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_eden_legal.json", "fields": ["REDEMPTION_CLAUSE", "RELATED_PARTY", "CONCENTRATION", "CASH_BURN_PRESSURE", "PRE_IPO_VALUATION"], "per_query": 5, "has_evidence_by_field": true, "hint": null}
   ```
2. **`parse_grep`**
   ```json
   {"path": "/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/01147_23-04-2020_伊登軟件_股份發售/full_parse.json", "hits": 0, "pages": []}
   ```
3. **`retrieve_section_evidence`**
   ```json
   {"intents": {"redemption": {"hits": 0, "pages": [], "route": [{"section_id": "risk_factors", "section_title": "風險因素", "start_page": 44, "end_page": 71, "confidence": 0.95}]}, "related_party": {"hits": 2, "pages": [279, 279], "route": [{"section_id": "business", "section_title": "業務", "start_page": 112, "end_page": 207, "confidence": 0.95}, {"section_id": "financial_information", "section_title": "財務資料", "start_page": 228, "end_page": 283, "confidence": 0.95}]}, "concentration": {"hits": 4, "pages": [184, 158, 183, 158], "route": [{"section_id": "business", "section_title": "業務", "start_page": 112, "end_page": 207, "confidence": 0.95}, {"section_id": "risk_factors", "section_title": "風險因素", "start_page": 44, "end_page": 71, "confidence": 0.95}, {"section_id": "financial_information", "section_title": "財務資料", "start_page": 228, "end_page": 283, "confidence": 0.95}]}}}
   ```
4. **`extract_legal`**
   ```json
   {"sections": {"3.1": {"exists": false, "skipped": null, "evidence_n": 0, "search_log": {"keywords_tried": ["赎回", "贖回", "对赌", "對賭", "回购", "回購", "优先股", "優先股", "领售", "領售", "撤资", "撤資", "贖回權", "可換股", "可转换可赎回", "可轉換可贖回", "股东协议", "股東協議", "特别权利", "特別權利", "赎回权终止", "特別權利終止"], "pages_scanned": [65, 224, 428, 430, 452], "raw_hits": 5, "filtered_noise": 0, "strong_hits": 0, "note": "已检索无命中强对赌/赎回/优先股模式"}, "top1_supplier_pct": null, "top5_supplier_pct": null}, "3.2": {"exists": false, "skipped": null, "evidence_n": 0, "search_log": null, "top1_supplier_pct": null, "top5_supplier_pct": null}, "3.3": {"exists": true, "skipped": null, "evidence_n": 5, "search_log": null, "top1_supplier_pct": 62.6, "top5_supplier_pct": 62.6}, "3.5": {"exists": null, "skipped": true, "evidence_n": 0, "search_log": null, "top1_supplier_pct": null, "top5_supplier_pct": null}}}
   ```
5. **`score_legal`**
   ```json
   {"risk_score": 25.0, "breakdown_n": 1}
   ```

### 3.6 分析结论

- 风险分 **25.0**（low）。打分来自披露基础分或规则命中（见 score_breakdown）。
- 3.1 对赌/赎回：exists=`False`，证据强度=`low`
- 3.2 关联交易：exists=`False`，占比=`None`。
- 3.3 集中度：exists=`True`，证据页=[15, 15, 16, 16, 11]。
- 3.5 管线风险按 non-biotech 正确跳过。

## 4. 改进建议

1. **[已做] 财务 LLM 主路径**：retrieve → extract_metrics → gates → analyze_finance(单次四维 LLM) → 可解释评分；规则打分降为 fallback（`--finance-rules-only`）。
2. **[已做] Gemma4 reasoning**：OpenRouter `reasoning.enabled`；日志区分 `[model_think]` / `[structured_reasoning]`。
3. **[已做] 推理日志落盘**：`logs/{doc}_{agent}_{ts}.log` + `.jsonl`（时间/文档/流程/工具skills/过程/结果/推理链）。
4. **[已做] 财务 BS 交叉校验**：若 TOTAL_ASSETS < NET_ASSETS，用 NET+LIAB 回填。
5. **法务检索源**：可用 `--use-live-retrieval`；`--use-llm` 做法务结构化增强。

---

_本报告由 `scripts/generate_analysis_report.py` 根据 Agent 结构化输出自动生成。_
