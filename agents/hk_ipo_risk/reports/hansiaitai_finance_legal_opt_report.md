# 翰思艾泰 — 财务/法务 Agent 结果分析报告

- 生成时间：2026-08-08 02:26:48
- 招股书：`03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf`
- doc_id：`hansiaitai`
- 参考基本面融合分：`79.62` （legal×0.45 + finance×0.55；总控未启用）
- 财务评分模式：`react+rules_floor`
- 推理日志：`/nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/logs/翰思艾泰_finance_20260808_022514.log`
- 说明：reference_fundamental_score = legal*0.45 + finance*0.55; master/cross_agent_features 为本轮占位，总控辩论未启用

## 1. 总览

| Agent | 风险分 (0-100↑风险) | 等级 | 摘要 |
|-------|---------------------|------|------|
| 财务穿透 | **100.0** | very_high | 翰思艾泰（18A生物科技）连续亏损且亏损扩大、CFO持续为负、现金跑道仅约20个月，未商业化且依赖融资，财务风险高。 |
| 法务合规 | **54.712896713646074** | medium | 法務 ReAct 自動收束（rule_checks_ready）：已完成 5 個 skill，彙總 20 個風險點 |

## 2. 财务穿透 Agent

### 2.1 得分与分解

| 代码 | 加分 | 规则 | 指标值 | 说明 | 证据页 |
|------|------|------|--------|------|--------|
| PROFIT_001 | +30.0 | 連續虧損且擴大 | NET_LOSS 2024=-116,922千元（2023=-85,160） | 連續兩年虧損且2024年虧損擴大37% | 562 |
| CASHFLOW_001 | +25.0 | 經營現金流持續為負 | CFO 2024=-104,894千元（2023=-51,994） | 經營活動現金流持續大幅為負且燒錢加劇 | 569 |
| CASH_RUNWAY | +20.0 | 現金跑道不足 | 現金跑道≈20.21個月 | 期末現金約150,000千元，月均燒錢約7,424千元，跑道不足兩年 | 569 |
| REV_NONCORE | +10.0 | 收入非產品收入 | OTHER_INCOME 2024=7,681千元 | 僅為其他收入及收益，非產品收入，尚未商業化 | 562 |
| CONTINUOUS_LOSS | +25.0 | doc§2.1 | — | （规则托底） | 562 |
| CFO_NEGATIVE | +15.0 | doc§2.3 | — | （规则托底） | 569 |
| CASH_RUNWAY_12_24 | +10.0 | doc§3.4 | — | （规则托底） | 563 |

### 2.2 四维分析（LLM）

#### `profitability_growth` — status=`analyzed`

发行人连续亏损且亏损幅度扩大：2023年淨虧損85,160千元，2024年擴大至116,922千元（+37%），2025年1-8月已虧損87,438千元。研發費用2024年達74,721千元持續攀升，而OTHER_INCOME（其他收入及收益）僅7,681千元，非產品收入，公司尚無產品銷售，收入端無實質支撐，盈利能力持續惡化。


#### `cash_flow` — status=`analyzed`

經營活動現金流持續為負且擴大：2023年-51,994千元、2024年-104,894千元，燒錢速度加快。期末現金約150,000千元，按月均燒錢約7,424千元測算，現金跑道僅約20.21個月，不足兩年，依賴後續融資支撐研發與營運，現金流風險顯著。


#### `solvency` — status=`analyzed`

淨資產持續下降：2024年216,604千元降至2025年8月144,791千元，降幅約33%；總負債由266,659千元升至299,507千元，累計虧損侵蝕淨資產，償債與資本結構穩健性趨弱。


#### `business_context` — status=`analyzed`

18A生物科技發行人尚未商業化，主表無產品收入，OTHER_INCOME為其他收入及收益而非產品收入。business_context證據檢索0 hit，標記為skipped/行業不適用。惟按18A特性，公司處於管線研發階段，依賴股權融資及現金跑道維繫營運，融資依賴度高為主要風險點。



### 2.3 推理链

**[structured_reasoning]**

翰思艾泰为18A生物科技发行人，连续两年大幅亏损且亏损扩大（2023年-85,160千元、2024年-116,922千元），CFO持续为负（2024年-104,894千元），现金跑道仅约20个月，且依赖融资输血。OTHER_INCOME（7,681千元）仅为其他收入及收益，并非产品收入，公司尚未实现商业化。business_context证据检索0 hit，故标注skipped/行业适用。综合各维度叠加为高风险。

**[model_think 摘录]**（全文见 logs）

> 现金跑道20.21个月。business_context检索0 hit，标记为skipped/证据不足。  现在整理四维分析与扣分项。  数据汇总： - 2023 NET_LOSS: -85160千元，2024: -116922千元，连续亏损扩大 - 2025_i1(8个月): -87438千元 - CFO 2023: -51994，2024: -104894，持续大幅为负 - OTHER_INCOME 2023: 6664, 2024: 7681 (小，非产品收入) - RD_EXP 2024: 74721 - CASH_EQ 2024: 161214, 2025_i1: 150000 - 现金跑道: 20.21个月 - NET_ASSETS 2024: 216604, 2025_i1: 144791 (下降) - TOTAL_LIAB 2024: 284867  is_unprofitable=true，score_breakdown不能为空，不能risk_score=0。  扣分项： 1. 连续亏损 (continuous_net_loss)，2024亏损116922千元 2. 

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

- intent=`business_context` query=`管线研发投入、商业化状态、融资依赖、现金跑道、产品收入` → 无可用章节

_本次未调用章节化上下文检索，或未命中证据。_

### 2.7 工具调用链

- 耗时：`31.227s`

1. **`retrieve_finance`**
   ```json
   {"turn": 1, "arguments": {"reason": "启动翰思艾泰18A生物科技发行人的财务风险穿透分析，需要检索三大财务主表数据。"}, "observation": {"ok": true, "source": "offline:/nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_finance.json", "tables": ["TBL_IS", "TBL_BS", "TBL_CF", "TBL_BS_COMPANY"], "tables_detail": [{"code": "TBL_IS", "nameZh": "合併損益表", "page": 562, "sourceType": "text", "excerpt": "截至12月31日止年度 截至8月31日止八個月\n\n附註 2023年 2024年 2024年 2025年\n人民幣千元 人民幣千元 人民幣千元 人民幣千元\n\n其他收入及收益 5 6,664 7,681 12,313 2,626\n研發成本 5 (46,663) (74,721) (50,523) (56,178)\n行政開支 6 (17,220) (46,192) (16,116) (27,436)\n其他", "nHits": 1}, {"code": "TBL_BS", "nameZh": "合併資產負債表", "page": 563, "sourceType": "text", "excerpt": "附註 於12月31日 於8月31日\n2023年 2024年 2025年\n人民幣千元 人民幣千元 人民幣千元\n\n非流動資產\n物業、廠房及設備 14 8,340 11,820 11,907\n使用權資產 15 15,661 12,309 10,525\n其他無形資產 16 558 447 587\n預付款項、其他應收款項及其他資產 18 531 330 330\n按公允價值計入損益（「按公允價值計入損益」）的", "nHits": 1}, {"code": "TBL_CF", "nameZh": "合併現金流量表", "page": 569, "sourceType": "table", "excerpt": "<table><tr><td rowspan=\"3\"></td><td colspan=\"2\">截至12月31日止年度</td><td colspan=\"2\">截至8月31日止八個月</td></tr><tr><td>2023年</td><td>2024年</td><td>2024年</td><td>2025年</td></tr><tr><td>人民幣千元</td><td>人民幣千元</td><t", "nHits": 1}, {"code": "TBL_BS_COMPANY", "nameZh": "公司層面資產負債表", "page": 572, "sourceType": "text", "excerpt": "附註 於12月31日 於8月31日\n2023年 2024年 2025年\n人民幣千元 人民幣千元 人民幣千元\n\n非流動資產\n物業、廠房及設備 14 6,405 10,099 10,393\n使用權資產 15 15,452 12,309 10,214\n於附屬公司的投資 17 78,438 78,438 78,438\n其他無形資產 18 - - 214\n預付款項、其他應收款項及其他資產 18 531 - ", "nHits": 1}], "skipped_fields": 0, "hint": "下一步可调用 extract_metrics"}, "duration_ms": 2234}
   ```
2. **`extract_metrics`**
   ```json
   {"turn": 2, "arguments": {"reason": "从三张主表抽取标准化财务指标以进行门控判断。"}, "observation": {"ok": true, "metric_keys": ["OTHER_INCOME", "RD_EXP", "SGA", "NET_LOSS", "NET_ASSETS", "CASH_EQ", "CV_PREF", "TOTAL_ASSETS", "TOTAL_LIAB", "CFO", "CFI", "CFF", "END_CASH"], "metric_keys_zh": [{"code": "OTHER_INCOME", "nameZh": "其他收入及收益"}, {"code": "RD_EXP", "nameZh": "研發費用"}, {"code": "SGA", "nameZh": "銷售及行政費用"}, {"code": "NET_LOSS", "nameZh": "期內虧損/利潤"}, {"code": "NET_ASSETS", "nameZh": "淨資產"}, {"code": "CASH_EQ", "nameZh": "現金及現金等價物"}, {"code": "CV_PREF", "nameZh": "可轉換可贖回優先股"}, {"code": "TOTAL_ASSETS", "nameZh": "總資產"}, {"code": "TOTAL_LIAB", "nameZh": "總負債"}, {"code": "CFO", "nameZh": "經營活動現金流淨額"}, {"code": "CFI", "nameZh": "投資活動現金流淨額"}, {"code": "CFF", "nameZh": "融資活動現金流淨額"}, {"code": "END_CASH", "nameZh": "年末現金餘額"}], "years": ["2023", "2024"], "metrics_summary": {"OTHER_INCOME": {"2023": 6664.0, "2024": 7681.0, "2024_i1": 12313.0, "2025_i1": 2626.0}, "NET_PROFIT_OR_LOSS": {"2023": -85160.0, "2024": -116922.0, "2024_i1": -48420.0, "2025_i1": -87438.0}, "CFO": {"2023": -51994.0, "2024": -104894.0, "2024_i1": -67918.0, "2025_i1": -59390.0}, "CASH_EQ": {"2023": 162000.0, "2024": 161214.0, "2025_i1": 150000.0}, "END_CASH": {"2023": 162000.0, "2024": 161214.0, "2024_i1": 181346.0, "2025_i1": 150000.0}, "TOTAL_ASSETS": {"2023": 586240.0, "2024": 501471.0, "2025_i1": 444298.0}, "TOTAL_LIAB": {"2023": 266659.0, "2024": 284867.0, "2025_i1": 299507.0}, "NET_ASSETS": {"2023": 319581.0, "2024": 216604.0, "2025_i1": 144791.0}}, "tables_detail": [{"code": "TBL_IS", "nameZh": "合併損益表", "page": 562, "sourceType": "text", "excerpt": "截至12月31日止年度 截至8月31日止八個月 附註 2023年 2024年 2024年 2025年 人民幣千元 人民幣千元 人民幣千元 人民幣千元 其他收入及收益 5 6,664 7,681 12,313 2,626 研發成本 5 (46,663) (74,721) (50,523) (56,178) 行政開支 6 "}, {"code": "TBL_BS", "nameZh": "合併資產負債表", "page": 563, "sourceType": "text", "excerpt": "附註 於12月31日 於8月31日 2023年 2024年 2025年 人民幣千元 人民幣千元 人民幣千元 非流動資產 物業、廠房及設備 14 8,340 11,820 11,907 使用權資產 15 15,661 12,309 10,525 其他無形資產 16 558 447 587 預付款項、其他應收款項及其他資產"}, {"code": "TBL_CF", "nameZh": "合併現金流量表", "page": 569, "sourceType": "table", "excerpt": "截至12月31日止年度 截至8月31日止八個月 2023年 2024年 2024年 2025年 人民幣千元 人民幣千元 人民幣千元 人民幣千元 經營活動所得現金流量 除税前虧損 (93,423) (122,820) (60,417) (99,933) 就下列各項作出調整： 利息開支 8 2,280 9,379 5,85"}, {"code": "TBL_BS_COMPANY", "nameZh": "公司層面資產負債表", "page": 572, "sourceType": "text", "excerpt": "附註 於12月31日 於8月31日 2023年 2024年 2025年 人民幣千元 人民幣千元 人民幣千元 非流動資產 物業、廠房及設備 14 6,405 10,099 10,393 使用權資產 15 15,452 12,309 10,214 於附屬公司的投資 17 78,438 78,438 78,438 其他無形資"}], "metric_note": "期內虧損/利潤(NET_LOSS/NET_PROFIT_OR_LOSS)：正數=盈利，負數=虧損。", "bs_reconcile": {"changed": false, "note": null}, "hint": "下一步可调用 derive_gates"}, "duration_ms": 7791}
   ```
3. **`derive_gates`**
   ```json
   {"turn": 3, "arguments": {"reason": "计算盈利状态、现金跑道和生物科技门控，判断是否触发18A未盈利路径。"}, "observation": {"ok": true, "gates": {"is_unprofitable": true, "continuous_net_loss": true, "latest_full_year_loss": true, "skip_3_4": false, "skip_3_4_reason": null, "skip_2_4": false, "issuer_type": "18a", "is_biotech_18a": true, "net_series": {"2023": -85160.0, "2024": -116922.0}, "profitability_basis": "NET_LOSS/年內利潤 series; positive=profit", "profitability_known": true, "profitability_status": "unprofitable"}, "fast_path": {"eligible": false, "reason": null}, "hint": "若未盈利可 calc_cash_runway；非主表主题可 retrieve_context_evidence；否则 submit"}, "duration_ms": 1006}
   ```
4. **`calc_cash_runway`**
   ```json
   {"turn": 4, "arguments": {"reason": "发行人连续亏损且未盈利，需测算现金跑道以评估融资与存续风险。"}, "observation": {"ok": true, "cash_burn": {"skipped": false, "reason": null, "CASH_RUNWAY_MONTHS": 20.21, "BURN_RATE_MONTHLY": 7423.75, "END_CASH": 150000.0}}, "duration_ms": 2451}
   ```
5. **`retrieve_context_evidence`**
   ```json
   {"turn": 4, "arguments": {"intent": "business_context", "query": "管线研发投入、商业化状态、融资依赖、现金跑道、产品收入", "section_hint": "business/industry/financing", "top_k": 5}, "observation": {"ok": true, "doc_id": "hansiaitai", "intent": "business_context", "query": "管线研发投入、商业化状态、融资依赖、现金跑道、产品收入", "n": 0, "route": [], "hits": [], "hint": "完整证据已保存到 state；submit 时引用 page/section/excerpt 即可"}, "duration_ms": 2451}
   ```
6. **`submit_finance_report`**
   ```json
   {"turn": 5, "arguments": {"risk_score": 85, "risk_level": "high", "reasoning": "翰思艾泰为18A生物科技发行人，连续两年大幅亏损且亏损扩大（2023年-85,160千元、2024年-116,922千元），CFO持续为负（2024年-104,894千元），现金跑道仅约20个月，且依赖融资输血。OTHER_INCOME（7,681千元）仅为其他收入及收益，并非产品收入，公司尚未实现商业化。business_context证据检索0 hit，故标注skipped/行业适用。综合各维度叠加为高风险。", "summary": "翰思艾泰（18A生物科技）连续亏损且亏损扩大、CFO持续为负、现金跑道仅约20个月，未商业化且依赖融资，财务风险高。", "dimensions": [{"dimension": "profitability_growth", "analysis": "发行人连续亏损且亏损幅度扩大：2023年淨虧損85,160千元，2024年擴大至116,922千元（+37%），2025年1-8月已虧損87,438千元。研發費用2024年達74,721千元持續攀升，而OTHER_INCOME（其他收入及收益）僅7,681千元，非產品收入，公司尚無產品銷售，收入端無實質支撐，盈利能力持續惡化。"}, {"dimension": "cash_flow", "analysis": "經營活動現金流持續為負且擴大：2023年-51,994千元、2024年-104,894千元，燒錢速度加快。期末現金約150,000千元，按月均燒錢約7,424千元測算，現金跑道僅約20.21個月，不足兩年，依賴後續融資支撐研發與營運，現金流風險顯著。"}, {"dimension": "solvency", "analysis": "淨資產持續下降：2024年216,604千元降至2025年8月144,791千元，降幅約33%；總負債由266,659千元升至299,507千元，累計虧損侵蝕淨資產，償債與資本結構穩健性趨弱。"}, {"dimension": "business_context", "analysis": "18A生物科技發行人尚未商業化，主表無產品收入，OTHER_INCOME為其他收入及收益而非產品收入。business_context證據檢索0 hit，標記為skipped/行業不適用。惟按18A特性，公司處於管線研發階段，依賴股權融資及現金跑道維繫營運，融資依賴度高為主要風險點。"}], "score_breakdown": [{"code": "PROFIT_001", "delta": 30, "rule_ref": "連續虧損且擴大", "metric_value": "NET_LOSS 2024=-116,922千元（2023=-85,160）", "note": "連續兩年虧損且2024年虧損擴大37%", "evidence_page": 562}, {"code": "CASHFLOW_001", "delta": 25, "rule_ref": "經營現金流持續為負", "metric_value": "CFO 2024=-104,894千元（2023=-51,994）", "note": "經營活動現金流持續大幅為負且燒錢加劇", "evidence_page": 569}, {"code": "CASH_RUNWAY", "delta": 20, "rule_ref": "現金跑道不足", "metric_value": "現金跑道≈20.21個月", "note": "期末現金約150,000千元，月均燒錢約7,424千元，跑道不足兩年", "evidence_page": 569}, {"code": "REV_NONCORE", "delta": 10, "rule_ref": "收入非產品收入", "metric_value": "OTHER_INCOME 2024=7,681千元", "note": "僅為其他收入及收益，非產品收入，尚未商業化", "evidence_page": 562}], "negative_findings": [{"code": "PROFIT_001", "rule_ref": "連續虧損", "description": "2023-2024連續虧損且2024年虧損擴大至116,922千元"}, {"code": "CASHFLOW_001", "rule_ref": "CFO持續為負", "description": "經營現金流持續為負，2024年達-104,894千元"}, {"code": "CASH_RUNWAY", "rule_ref": "現金跑道", "description": "現金跑道僅約20.21個月，依賴後續融資"}]}, "observation": {"ok": true, "finished": true, "risk_score": 100.0, "risk_level": "very_high", "warnings": ["rules_floor_added:CONTINUOUS_LOSS", "rules_floor_added:CFO_NEGATIVE", "rules_floor_added:CASH_RUNWAY_12_24"], "summary": "翰思艾泰（18A生物科技）连续亏损且亏损扩大、CFO持续为负、现金跑道仅约20个月，未商业化且依赖融资，财务风险高。", "rules_floor": {"rules_score": 50.0, "rules_score_deduped": 135.0, "llm_score": 85.0, "final_score": 100.0, "flags": {"continuous_net_loss": true, "latest_full_year_loss": true, "cfo_persistently_negative": true, "gp_margin_drop_gt_5pp": false, "runway_lt_12": false, "runway_12_24": true, "burn_yoy_up_gt_30": false}}, "submit_recovered": false}, "duration_ms": 15803}
   ```

### 2.8 分析结论

- 评分模式 **react+rules_floor**；风险分 **100.0**（very_high）。门控：未盈利=`True`，跳过3.4=`False`（None），跳过2.4=`False`（None）。
- 模型 think 状态：`ok`（全文见推理日志 `[model_think]`）。
- 结构化推理摘要：翰思艾泰为18A生物科技发行人，连续两年大幅亏损且亏损扩大（2023年-85,160千元、2024年-116,922千元），CFO持续为负（2024年-104,894千元），现金跑道仅约20个月，且依赖融资输血。OTHER_INCOME（7,681千元）仅为其他收入及收益，并非产品收入，公司尚未实现商业化。business_context证据检索0 hit，故标注skipped/行业适用。综合各维度叠加为高风险。
- LLM 摘要：翰思艾泰（18A生物科技）连续亏损且亏损扩大、CFO持续为负、现金跑道仅约20个月，未商业化且依赖融资，财务风险高。
- 期内利润（NET_LOSS 字段存利润序列，正数=盈利）：2023=-85,160、2024=-116,922。
- 主表证据定位：TBL_IS@p562, TBL_BS@p563, TBL_CF@p569, TBL_BS_COMPANY@p572。
- 推理日志：`/nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/logs/翰思艾泰_finance_20260808_022514.log`

### 2.9 阴性发现（低风险说明）

- **PROFIT_001**（連續虧損）：2023-2024連續虧損且2024年虧損擴大至116,922千元
- **CASHFLOW_001**（CFO持續為負）：經營現金流持續為負，2024年達-104,894千元
- **CASH_RUNWAY**（現金跑道）：現金跑道僅約20.21個月，依賴後續融資

## 3. 法务合规 Agent

### 3.1 得分与分解

| 代码 | 加分 | 规则 | 指标值 | 说明 | 证据页 |
|------|------|------|--------|------|--------|
| RIGHTS_CLEANUP_INCOMPLETE | +20.0 | llm§legal_shareholder_rights | — | 特別權利（包括購回權、反攤薄權等）僅在上市申請提交時終止購回權，其他特別權利於上市後終止，且若上市失敗將自動恢復，未在上市前完整解除。 | 262 |
| REDEMPTION_TRIGGER_IMMINENT | +18.0 | llm§legal_shareholder_rights | 4個月 | 贖回權觸發期限為2025年12月31日，距招股書日期（2025年8月31日）不足12個月，且上市進程存在不確定性，可能觸發贖回義務。（覆盖规则同主题项） | 262 |
| RELATED_PARTY_TERM | +8.0 | llm§legal_related_party | 5年 | 關連交易協議期限超過三年，需依賴特殊情況豁免，存在合規風險 | 416 |
| IP_PATENT_REJECTION | +8.0 | llm§legal_contracts_and_ip | — | FcRn專利申請在中國被國家知識產權局駁回，但法律顧問認為未必導致同族專利在其他司法權區無效，且未見直接商業化受阻證據。 | 386 |
| GOVERNANCE_CONTROL_GT_50 | +6.0 | llm§legal_governance | 55.89 | 控股股東集團持股約55.89%，超過50%，對公司決策有重大影響力，可能損害少數股東利益。 | 115 |
| CONCENTRATION_DISCLOSURE | +6.0 | doc§3.3 | — | 存在客户/供应商集中度披露 | 28, 29 |
| PIPELINE_DISCLOSURE | +6.0 | doc§3.5 | — | 存在核心产品/管线进度披露 | 14, 16, 17, 20, 27 |
| SOCIAL_INSURANCE_COMPLIANCE | +1.8 | llm§legal_regulatory_litigation | — | 社會保險及住房公積金供款可能不足，但公司已承諾補繳並制定內部監控政策，風險相對較小。 | 403 |

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

特別權利（包括購回權、反攤薄權等）僅在上市申請提交時終止購回權，其他特別權利於上市後終止，且若上市失敗將自動恢復，未在上市前完整解除。


#### `REDEMPTION_TRIGGER_IMMINENT`（+18.0，llm§legal_shareholder_rights）

贖回權觸發期限為2025年12月31日，距招股書日期（2025年8月31日）不足12個月，且上市進程存在不確定性，可能觸發贖回義務。（覆盖规则同主题项）


#### `RELATED_PARTY_TERM`（+8.0，llm§legal_related_party）

關連交易協議期限超過三年，需依賴特殊情況豁免，存在合規風險


#### `IP_PATENT_REJECTION`（+8.0，llm§legal_contracts_and_ip）

FcRn專利申請在中國被國家知識產權局駁回，但法律顧問認為未必導致同族專利在其他司法權區無效，且未見直接商業化受阻證據。


#### `GOVERNANCE_CONTROL_GT_50`（+6.0，llm§legal_governance）

控股股東集團持股約55.89%，超過50%，對公司決策有重大影響力，可能損害少數股東利益。


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

#### `SOCIAL_INSURANCE_COMPLIANCE`（+1.8，llm§legal_regulatory_litigation）

社會保險及住房公積金供款可能不足，但公司已承諾補繳並制定內部監控政策，風險相對較小。


### 3.5 工具调用链

- 耗时：`59.216s`

1. **`retrieve_legal`**
   ```json
   {"turn": 1, "arguments": {"reason": "初始化翰思艾泰(18A)法务证据包，为后续5个专项合规审查提供检索基线与页码索引"}, "observation": {"ok": true, "source": "offline:/nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_legal.json", "fields": ["REDEMPTION_CLAUSE", "RELATED_PARTY", "CONCENTRATION", "CASH_BURN_PRESSURE", "PIPELINE_RISK", "PRE_IPO_VALUATION"], "grep_hits": 0, "grep_pages_sample": [], "has_evidence_by_field": true, "skills_available": ["legal_governance", "legal_shareholder_rights", "legal_related_party", "legal_contracts_and_ip", "legal_regulatory_litigation"], "search_quota": 2, "search_used": 0, "hint": "下一步逐个调用 run_legal_skill（共5个）；search_legal_evidence 全程配额≤2 次，证据不足时精选补检，rule_checks 后尽快 submit"}, "duration_ms": 1846}
   ```
2. **`run_legal_skill`**
   ```json
   {"turn": 2, "arguments": {"skill_name": "legal_governance", "reason": "审查翰思艾泰(18A)的股权结构与公司治理，重点关注VIE/双层架构、董事会构成、特别表决权等治理风险"}, "observation": {"ok": true, "skill": "legal_governance", "exists": true, "confidence": "high", "n_risk_points": 3, "risk_points": [{"code": "GOVERNANCE_CONTROL_GT_50", "level": "high", "confidence": "high", "evidence_page": 115, "description": "控股股東集團持股約55.89%，超過50%，對公司決策有重大影響力，可能損害少數股東利益。"}, {"code": "GOVERNANCE_CONCERT_PARTY", "level": "medium", "confidence": "high", "evidence_page": 254, "description": "與武漢瀚中及杭州甘明訂立一致行動協議，以維持對杭州翰思的控制權，協議尚未終止，可能影響公司治理的獨立性。"}, {"code": "GOVERNANCE_BOARD_INDEPENDENCE", "level": "low", "confidence": "high", "evidence_page": 272, "description": "董事會結構未詳細披露，但存在執行董事持股，可能影響獨立性，需關注獨立非執行董事比例。"}], "features": {"controlling_shareholder": "蔡張生物科技、翰思生物醫藥（香港）及武漢翰思", "control_pct": 55.89, "concert_party": true, "ab_shares": false, "board_note": "董事會結構未在原文中詳細描述，但存在執行董事肖女士持股0.01%"}, "negative_findings_n": 1, "evidence_pages": [80, 81, 115, 254, 272], "search_quota": 2, "search_used": 0, "error": null, "hint": "证据充分，可继续下一个 skill"}, "duration_ms": 2157}
   ```
3. **`run_legal_skill`**
   ```json
   {"turn": 2, "arguments": {"skill_name": "legal_shareholder_rights", "reason": "审查翰思艾泰的对赌赎回条款、优先股权利及上市前投资权利清理情况"}, "observation": {"ok": true, "skill": "legal_shareholder_rights", "exists": true, "confidence": "medium", "n_risk_points": 5, "risk_points": [{"code": "REDEMPTION_TRIGGER_IMMINENT", "level": "high", "confidence": "high", "evidence_page": 262, "description": "贖回權觸發期限為2025年12月31日，距招股書日期（2025年8月31日）不足12個月，且上市進程存在不確定性，可能觸發贖回義務。"}, {"code": "REDEMPTION_AMOUNT_HIGH", "level": "high", "confidence": "high", "evidence_page": 497, "description": "贖回負債人民幣138.5百萬元，佔流動負債淨額（人民幣15.2百萬元）比例極高，且公司已錄得流動負債淨額，贖回義務可能對財務狀況造成重大影響。"}, {"code": "RIGHTS_CLEANUP_INCOMPLETE", "level": "high", "confidence": "high", "evidence_page": 262, "description": "特別權利（包括購回權、反攤薄權等）僅在上市申請提交時終止購回權，其他特別權利於上市後終止，且若上市失敗將自動恢復，未在上市前完整解除。"}, {"code": "REDEMPTION_LIABILITY_CLASSIFICATION", "level": "medium", "confidence": "high", "evidence_page": 80, "description": "贖回負債被分類為流動負債，導致流動負債淨額，可能影響公司持續經營能力評估，但董事認為未來十二個月無現金流出。"}, {"code": "REDEMPTION_HIGH", "level": "high", "confidence": "medium", "evidence_page": 262, "description": "贖回/對賭觸發期限剩餘約 4 個月 (<12個月)（阈值判定自动补充）"}], "features": {"exists_redemption": true, "trigger_condition": "上市申請被聯交所撤回或駁回；或中國證監會備案被駁回；或未能於2025年12月31日前完成上市（以較早者為準）", "redemption_price_or_rate": "按贖回金額的攤銷成本確認，未明確利率", "amount": "人民幣138.5百萬元（截至2025年8月31日）", "remaining_months": 4, "rights_cleared_pre_ipo": false, "pre_ipo_rounds": 3}, "negative_findings_n": 1, "evidence_pages": [80, 262, 271, 477, 497], "search_quota": 2, "search_used": 0, "error": null, "hint": "证据充分，可继续下一个 skill"}, "duration_ms": 2157}
   ```
4. **`run_legal_skill`**
   ```json
   {"turn": 3, "arguments": {"reason": "审查翰思艾泰的关联交易合规性，重点关注是否存在未按上市规则第十四A章披露或未获独立股东批准的关联交易", "skill_name": "legal_related_party"}, "observation": {"ok": true, "skill": "legal_related_party", "exists": true, "confidence": "high", "n_risk_points": 3, "risk_points": [{"code": "RELATED_PARTY_EXEMPT", "level": "low", "confidence": "high", "evidence_page": 424, "description": "關連交易獲完全豁免，但存在依賴豁免條款的潛在風險"}, {"code": "RELATED_PARTY_TERM", "level": "medium", "confidence": "high", "evidence_page": 416, "description": "關連交易協議期限超過三年，需依賴特殊情況豁免，存在合規風險"}, {"code": "RELATED_PARTY_APPROVAL", "level": "low", "confidence": "high", "evidence_page": 425, "description": "非獲豁免持續關連交易需獨立股東批准，但已獲董事及保薦人確認公平合理"}], "features": {"parties": ["中美華世通（關連方）", "發行人"], "txn_types": ["採購（原材料供應）", "服務（HX301活性藥品成分及穩定性測試）"], "max_ratio_pct": 5, "ratio_rising": false, "waiver": "完全豁免（低於5%及300萬港元）", "fair_price": "董事及獨家保薦人認為公平合理、按一般商業條款", "dependency": false}, "negative_findings_n": 2, "evidence_pages": [415, 416, 424, 425], "search_quota": 2, "search_used": 0, "error": null, "hint": "证据充分，可继续下一个 skill"}, "duration_ms": 2005}
   ```
5. **`run_legal_skill`**
   ```json
   {"turn": 3, "arguments": {"reason": "审查翰思艾泰的重大合同、知识产权及管线相关风险", "skill_name": "legal_contracts_and_ip"}, "observation": {"ok": true, "skill": "legal_contracts_and_ip", "exists": true, "confidence": "high", "n_risk_points": 4, "risk_points": [{"code": "IP_PATENT_REJECTION", "level": "medium", "confidence": "high", "evidence_page": 386, "description": "FcRn專利申請在中國被國家知識產權局駁回，但法律顧問認為未必導致同族專利在其他司法權區無效，且未見直接商業化受阻證據。"}, {"code": "IP_MAINTENANCE_RISK", "level": "medium", "confidence": "high", "evidence_page": 93, "description": "專利維護需定期繳納費用並遵守程序，若未遵守可能導致專利失效，影響競爭地位。"}, {"code": "IP_THIRD_PARTY_CLAIMS", "level": "medium", "confidence": "high", "evidence_page": 98, "description": "前僱員席先生可能與公司就專利產生潛在糾紛，且知識產權可能受第三方質疑或侵權。"}, {"code": "IP_FTO_LIMITED", "level": "low", "confidence": "high", "evidence_page": 386, "description": "僅對核心產品及主要產品在中國進行自由運營分析，HX044因早期未進行，且未在海外進行FTO分析。"}], "features": {"material_contracts": ["HX008股權轉讓協議（與中山康方合作）"], "exclusive_deals": false, "core_tech_self_owned": true, "license_in": false, "ip_note": "FcRn專利申請在中國被駁回，但法律顧問認為未必影響同族有效性；核心產品專利覆蓋良好"}, "negative_findings_n": 2, "evidence_pages": [74, 92, 93, 98, 381, 386, 407], "search_quota": 2, "search_used": 0, "error": null, "hint": "证据充分，可继续下一个 skill"}, "duration_ms": 2005}
   ```
6. **`run_legal_skill`**
   ```json
   {"turn": 4, "arguments": {"reason": "审查翰思艾泰的监管处罚、诉讼仲裁及相关合规风险", "skill_name": "legal_regulatory_litigation"}, "observation": {"ok": true, "skill": "legal_regulatory_litigation", "exists": true, "confidence": "high", "n_risk_points": 5, "risk_points": [{"code": "SOCIAL_INSURANCE_COMPLIANCE", "level": "low", "confidence": "high", "evidence_page": 403, "description": "社會保險及住房公積金供款可能不足，但公司已承諾補繳並制定內部監控政策，風險相對較小。"}, {"code": "REGULATORY_CHANGE_RISK", "level": "medium", "confidence": "high", "evidence_page": 83, "description": "中國生物製藥行業監管架構持續演變，可能增加合規成本或延遲藥物開發，但無具體事件。"}, {"code": "US_FDA_COMPLIANCE_RISK", "level": "medium", "confidence": "high", "evidence_page": 237, "description": "美國FDA監管嚴格，未能遵守可能導致行政訴訟或制裁，但無具體違規事件。"}, {"code": "ANTI_FRAUD_LAW_RISK", "level": "medium", "confidence": "high", "evidence_page": 87, "description": "受反回扣及虛假索賠等法律約束，違反可能導致刑事或民事制裁，但無具體指控。"}, {"code": "HUMAN_GENETIC_RESOURCE_RISK", "level": "medium", "confidence": "high", "evidence_page": 86, "description": "人類遺傳資源處理可能未完全合規，存在行政處罰風險，但無具體違規。"}], "features": {"major_litigation": false}, "negative_findings_n": 2, "evidence_pages": [83, 85, 86, 87, 233, 237, 403, 406], "search_quota": 2, "search_used": 0, "error": null, "hint": "证据充分，可继续下一个 skill"}, "duration_ms": 1010}
   ```
7. **`run_rule_checks`**
   ```json
   {"turn": 5, "arguments": {"reason": "对5个专项审查结果运行规则引擎交叉核对，确认各风险点的命中情况与覆盖缺口"}, "observation": {"ok": true, "rules_score": 51.0, "rules_level": "medium", "flags": {"redemption_high": false, "redemption_medium": true, "related_party_ratio_gt_30": false, "related_party_rising": false, "concentration_high": false, "pipeline_high": false, "valuation_inversion": false}, "breakdown": [{"code": "REDEMPTION_MEDIUM", "delta": 12.0, "rule_ref": "doc§3.1"}, {"code": "RELATED_PARTY_DISCLOSURE", "delta": 15.0, "rule_ref": "doc§3.2"}, {"code": "CONCENTRATION_DISCLOSURE", "delta": 12.0, "rule_ref": "doc§3.3"}, {"code": "PIPELINE_DISCLOSURE", "delta": 12.0, "rule_ref": "doc§3.5"}], "coverage_hints": [], "search_quota": 0, "search_used": 0, "ready_to_submit": true, "n_skills": 5, "hint": "无覆盖缺口且 5 个 skill 已完成。系统将服务端交卷（无需再写长 risk_points）；禁止再 search。"}, "duration_ms": 1641}
   ```

### 3.6 分析结论

- 风险分 **54.712896713646074**（medium）。打分来自披露基础分或规则命中（见 score_breakdown）。
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
