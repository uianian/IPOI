# 翰思艾泰 — 财务/法务 Agent 结果分析报告

- 生成时间：2026-08-08 03:41:11
- 招股书：`03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf`
- doc_id：`hansiaitai`
- 参考基本面融合分：`None` （legal×0.45 + finance×0.55；总控未启用）
- 财务评分模式：`react+rules_floor`
- 推理日志：`/nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/logs/翰思艾泰_finance_20260808_034024.log`
- 说明：—

## 1. 总览

| Agent | 风险分 (0-100↑风险) | 等级 | 摘要 |
|-------|---------------------|------|------|
| 财务穿透 | **55.0** | medium | 翰思艾泰(18A生物科技)未商業化、連續兩年虧損擴大且經營現金流持續為負，現金跑道約20.2個月，流動性依賴全球發售融資，綜合風險中等（55分）。 |

## 2. 财务穿透 Agent

### 2.1 得分与分解

| 代码 | 加分 | 规则 | 指标值 | 说明 | 证据页 |
|------|------|------|--------|------|--------|
| CONTINUOUS_LOSS | +25.0 | doc§2.1 | — | （规则托底） | 562 |
| CFO_NEGATIVE | +15.0 | doc§2.3 | — | （规则托底） | 569 |
| CASH_RUNWAY_12_24 | +10.0 | doc§3.4 | — | （规则托底） | 563 |
| OTHER_SOLVENCY_RISK | +5.0 | 流動負債淨額風險 | 流動負債淨額=-15.2百萬元（普通股贖回負債138.5百萬） | 截至2025年8月31日流動負債淨額為負，流動性壓力上升 | 80 |

### 2.2 四维分析（LLM）

#### `profitability_growth` — status=`analyzed`

連續虧損且虧損擴大：2023年淨虧損-85,160千元、2024年淨虧損-116,922千元人民幣。無產品收入，OTHER_INCOME（其他收入及收益）2023年6,664千元、2024年7,681千元，屬非產品收入，遠不足以覆蓋虧損。研發費用由46,663千元增至74,721千元，行政開支由17,220千元增至46,192千元，支出擴張快於收入，尚未實現盈利，屬18A未商業化階段基線特徵。


#### `cash_flow` — status=`analyzed`

經營活動現金流持續為負：2023年-51,994千元、2024年-104,894千元、截至2025年8月止八個月-59,390千元，流出規模持續擴大。截至2025年8月31日現金及現金等價物約150,000千元，按月度消耗約7,424千元計，現金跑道約20.2個月（介於12-24個月），若無後續融資，資金不足以支撐兩年以上持續運營，融資依賴度偏高。


#### `solvency` — status=`analyzed`

總負債由2023年266,659千元增至2024年284,867千元及2025年8月299,507千元，淨資產由319,581千元降至144,791千元。截至2025年8月31日錄得流動負債淨額約-15.2百萬元，主要源於普通股贖回負債138.5百萬元入賬為流動負債（其贖回權將於上市完成前一日終止）。整體償債與流動性壓力上升，依賴上市融資緩解。


#### `business_context` — status=`analyzed`

屬18A生物科技，尚未商業化，無產品銷售收入，資金主要用於候選藥物臨床前及臨床開發、行政開支及其他經常性開支。現金來源高度依賴全球發售所得款項淨額、首次公開發售前投資及轉讓泰州翰中股權所得款項。候選藥物商業化前的持續虧損屬基線事實，需配合現金跑道與CFO一併衡量其資金可持續性。



### 2.3 推理链

**[structured_reasoning]**

翰思艾泰為18A未商業化生物科技公司，連續兩年錄得虧損且虧損擴大（2023年-85.2百萬、2024年-116.9百萬人民幣），無產品收入，OTHER_INCOME僅為其他收入及收益而非產品收入。經營活動現金流持續為負（2024年-104.9百萬），現金消耗主要投向臨床開發與行政開支。截至2025年8月31日現金及現金等價物約150.0百萬元，按月度消耗約7.4百萬元計，現金跑道約20.2個月（落在12-24個月區間）。流動負債淨額-15.2百萬元源於普通股贖回負債（上市前自動終止），流動性依賴全球發售所得款項及股權轉讓。綜合判斷為中等風險。

**[model_think 摘录]**（全文见 logs）

> 我已经收集了足够的信息。现在整理分析。  关键指标： - NET_LOSS: 2023 -85,160千元, 2024 -116,922千元（持续扩大亏损） - OTHER_INCOME: 2023 6,664, 2024 7,681 (远小于亏损，非产品收入) - RD_EXP: 2023 46,663, 2024 74,721 - CFO: 2023 -51,994, 2024 -104,894, 2025_i1 -59,390（持续为负） - END_CASH: 2025_i1 150,000千元 - 现金跑道: 20.21个月（介于12-24个月）→ CASH_RUNWAY_12_24 (+10) - 连续亏损 → CONTINUOUS_LOSS (+25) - CFO持续为负 → CFO_NEGATIVE (+15) - 流动资产净额 -15.2百万（普通股赎回负债）→ 偿债风险  无产品收入，OTHER_INCOME非产品收入。  扣分项： - CONTINUOUS_LOSS(+25) - CFO_NEGATIVE(+15) - CASH_RUNWAY_12_24(+10)

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

- intent=`financing_dependency` query=`融資/資金需求/營運資金/所得款項用途/現金消耗` → financial_information@p474-507, risk_factors@p73-126, history_and_corporate_structure@p241-276

| 意图章节 | 页码 | 类型 | 分数 | 匹配词 | 摘录 |
|---|---:|---|---:|---|---|
| risk_factors | 80 | text | 4.386 | 融資, 資金需求, 營運資金 | 截至2023年及2024年12月31日止年度以及截至2024年及2025年8月31日止八個月，我們經營活動所用現金流量淨額分別為人民幣52.0百萬元、人民幣104.9百萬元、人民幣67.9百萬元及人民幣59.4百萬元。我們的經營活動可能會不時產生現金流出淨額。有關詳情，請參閱本招股章程「財務資料－流動資金及資本資源－經營活動所用現金流量淨額」。我們對資本資源足以支持營運的時間段的預測屬於前瞻性陳述，涉及風險及不確定性。我們作出該估計所依據的假設可能會被證明有誤，且我們耗盡現有 |
| financial_information | 498 | text | 4.3818 | 融資, 資金需求, 營運資金 | 我們的主要現金用途乃為候選藥物的臨床前及臨床開發、行政開支及其他經常性開支提供資金。截至2023年及2024年12月31日止年度以及截至2024年及2025年8月31日止八個月，我們經營活動所用現金流淨額分別為人民幣52.0百萬元、人民幣104.9百萬元、人民幣67.9百萬元及人民幣59.4百萬元，乃主要由於我們於往績記錄期間產生大量研發成本及管理開支。我們的經營現金流量將繼續受到研發成本的影響。於往績記錄期間及直至最後實際可行日期，我們主要通過向樂普轉讓我們於泰州翰中的股權 |
| risk_factors | 80 | text | 4.3721 | 融資, 資金需求, 營運資金 | 截至2025年8月31日，我們錄得流動負債淨額人民幣15.2百萬元，此乃主要由於普通股贖回負債人民幣138.5百萬元已入賬為流動負債，而其贖回權將於上市完成前一日自動終止。流動負債淨額狀況可能使我們面臨流動性不足的風險。此進而使我們須尋求充足的融資管道。倘我們無法維持充足的營運資金或取得足夠的股權或債務融資以滿足我們的資金需求，我們可能無法按計劃持續運營，並被迫縮減營運規模，此可能會對我們的業務、財務狀況、經營業績及前景產生重大不利影響。 |
| financial_information | 502 | text | 3.3653 | 融資, 現金消耗 | 展望未來，我們相信我們的流動性需求將通過全球發售所得款項淨額、首次公開發售前投資及轉讓我們於泰州翰中的股權的所得款項予以滿足。截至2025年8月31日，我們的現金及現金等價物為人民幣150.0百萬元。除了可能獲得的銀行借款外，我們於上市前並無計劃進行重大外部債務融資。假設未來平均現金消耗率為2024年水平 |
| financial_information | 498 | text | 3.3646 | 融資, 資金需求 | 我們的管理層密切監控現金及現金結餘的用途，並致力為我們的營運維持穩健的流動資金狀況。展望未來，我們相信全球發售所得款項淨額、來自潛在合作安排的資金以及候選藥物商業化後我們營運所產生的現金將共同滿足我們的流動資金需求。隨著我們業務的不斷擴張，我們可能需要通過公開或私人發售、債務融資、合作安排或 |

### 2.7 工具调用链

- 耗时：`30.983s`

1. **`retrieve_finance`**
   ```json
   {"turn": 1, "arguments": {"reason": "开始对翰思艾泰(18A生物科技)进行财务风险穿透分析，首先检索三张财务主表"}, "observation": {"ok": true, "source": "offline:/nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_finance.json", "tables": ["TBL_IS", "TBL_BS", "TBL_CF", "TBL_BS_COMPANY"], "tables_detail": [{"code": "TBL_IS", "nameZh": "合併損益表", "page": 562, "sourceType": "text", "excerpt": "截至12月31日止年度 截至8月31日止八個月\n\n附註 2023年 2024年 2024年 2025年\n人民幣千元 人民幣千元 人民幣千元 人民幣千元\n\n其他收入及收益 5 6,664 7,681 12,313 2,626\n研發成本 5 (46,663) (74,721) (50,523) (56,178)\n行政開支 6 (17,220) (46,192) (16,116) (27,436)\n其他", "nHits": 1}, {"code": "TBL_BS", "nameZh": "合併資產負債表", "page": 563, "sourceType": "text", "excerpt": "附註 於12月31日 於8月31日\n2023年 2024年 2025年\n人民幣千元 人民幣千元 人民幣千元\n\n非流動資產\n物業、廠房及設備 14 8,340 11,820 11,907\n使用權資產 15 15,661 12,309 10,525\n其他無形資產 16 558 447 587\n預付款項、其他應收款項及其他資產 18 531 330 330\n按公允價值計入損益（「按公允價值計入損益」）的", "nHits": 1}, {"code": "TBL_CF", "nameZh": "合併現金流量表", "page": 569, "sourceType": "table", "excerpt": "<table><tr><td rowspan=\"3\"></td><td colspan=\"2\">截至12月31日止年度</td><td colspan=\"2\">截至8月31日止八個月</td></tr><tr><td>2023年</td><td>2024年</td><td>2024年</td><td>2025年</td></tr><tr><td>人民幣千元</td><td>人民幣千元</td><t", "nHits": 1}, {"code": "TBL_BS_COMPANY", "nameZh": "公司層面資產負債表", "page": 572, "sourceType": "text", "excerpt": "附註 於12月31日 於8月31日\n2023年 2024年 2025年\n人民幣千元 人民幣千元 人民幣千元\n\n非流動資產\n物業、廠房及設備 14 6,405 10,099 10,393\n使用權資產 15 15,452 12,309 10,214\n於附屬公司的投資 17 78,438 78,438 78,438\n其他無形資產 18 - - 214\n預付款項、其他應收款項及其他資產 18 531 - ", "nHits": 1}], "skipped_fields": 0, "hint": "下一步可调用 extract_metrics"}, "duration_ms": 1202}
   ```
2. **`extract_metrics`**
   ```json
   {"turn": 2, "arguments": {"reason": "从翰思艾泰财务主表抽取营收、净利、研发、现金、CFO等标准指标"}, "observation": {"ok": true, "metric_keys": ["OTHER_INCOME", "RD_EXP", "SGA", "NET_LOSS", "NET_ASSETS", "CASH_EQ", "CV_PREF", "TOTAL_ASSETS", "TOTAL_LIAB", "CFO", "CFI", "CFF", "END_CASH"], "metric_keys_zh": [{"code": "OTHER_INCOME", "nameZh": "其他收入及收益"}, {"code": "RD_EXP", "nameZh": "研發費用"}, {"code": "SGA", "nameZh": "銷售及行政費用"}, {"code": "NET_LOSS", "nameZh": "期內虧損/利潤"}, {"code": "NET_ASSETS", "nameZh": "淨資產"}, {"code": "CASH_EQ", "nameZh": "現金及現金等價物"}, {"code": "CV_PREF", "nameZh": "可轉換可贖回優先股"}, {"code": "TOTAL_ASSETS", "nameZh": "總資產"}, {"code": "TOTAL_LIAB", "nameZh": "總負債"}, {"code": "CFO", "nameZh": "經營活動現金流淨額"}, {"code": "CFI", "nameZh": "投資活動現金流淨額"}, {"code": "CFF", "nameZh": "融資活動現金流淨額"}, {"code": "END_CASH", "nameZh": "年末現金餘額"}], "years": ["2023", "2024"], "metrics_summary": {"OTHER_INCOME": {"2023": 6664.0, "2024": 7681.0, "2024_i1": 12313.0, "2025_i1": 2626.0}, "NET_PROFIT_OR_LOSS": {"2023": -85160.0, "2024": -116922.0, "2024_i1": -48420.0, "2025_i1": -87438.0}, "CFO": {"2023": -51994.0, "2024": -104894.0, "2024_i1": -67918.0, "2025_i1": -59390.0}, "CASH_EQ": {"2023": 162000.0, "2024": 161214.0, "2025_i1": 150000.0}, "END_CASH": {"2023": 162000.0, "2024": 161214.0, "2024_i1": 181346.0, "2025_i1": 150000.0}, "TOTAL_ASSETS": {"2023": 586240.0, "2024": 501471.0, "2025_i1": 444298.0}, "TOTAL_LIAB": {"2023": 266659.0, "2024": 284867.0, "2025_i1": 299507.0}, "NET_ASSETS": {"2023": 319581.0, "2024": 216604.0, "2025_i1": 144791.0}}, "tables_detail": [{"code": "TBL_IS", "nameZh": "合併損益表", "page": 562, "sourceType": "text", "excerpt": "截至12月31日止年度 截至8月31日止八個月 附註 2023年 2024年 2024年 2025年 人民幣千元 人民幣千元 人民幣千元 人民幣千元 其他收入及收益 5 6,664 7,681 12,313 2,626 研發成本 5 (46,663) (74,721) (50,523) (56,178) 行政開支 6 "}, {"code": "TBL_BS", "nameZh": "合併資產負債表", "page": 563, "sourceType": "text", "excerpt": "附註 於12月31日 於8月31日 2023年 2024年 2025年 人民幣千元 人民幣千元 人民幣千元 非流動資產 物業、廠房及設備 14 8,340 11,820 11,907 使用權資產 15 15,661 12,309 10,525 其他無形資產 16 558 447 587 預付款項、其他應收款項及其他資產"}, {"code": "TBL_CF", "nameZh": "合併現金流量表", "page": 569, "sourceType": "table", "excerpt": "截至12月31日止年度 截至8月31日止八個月 2023年 2024年 2024年 2025年 人民幣千元 人民幣千元 人民幣千元 人民幣千元 經營活動所得現金流量 除税前虧損 (93,423) (122,820) (60,417) (99,933) 就下列各項作出調整： 利息開支 8 2,280 9,379 5,85"}, {"code": "TBL_BS_COMPANY", "nameZh": "公司層面資產負債表", "page": 572, "sourceType": "text", "excerpt": "附註 於12月31日 於8月31日 2023年 2024年 2025年 人民幣千元 人民幣千元 人民幣千元 非流動資產 物業、廠房及設備 14 6,405 10,099 10,393 使用權資產 15 15,452 12,309 10,214 於附屬公司的投資 17 78,438 78,438 78,438 其他無形資"}], "metric_note": "期內虧損/利潤(NET_LOSS/NET_PROFIT_OR_LOSS)：正數=盈利，負數=虧損。", "bs_reconcile": {"changed": false, "note": null}, "hint": "下一步可调用 derive_gates"}, "duration_ms": 1191}
   ```
3. **`derive_gates`**
   ```json
   {"turn": 3, "arguments": {"reason": "计算翰思艾泰盈利状态、现金跑道与生物科技门控"}, "observation": {"ok": true, "gates": {"is_unprofitable": true, "continuous_net_loss": true, "latest_full_year_loss": true, "skip_3_4": false, "skip_3_4_reason": null, "skip_2_4": false, "issuer_type": "18a", "is_biotech_18a": true, "net_series": {"2023": -85160.0, "2024": -116922.0}, "profitability_basis": "NET_LOSS/年內利潤 series; positive=profit", "profitability_known": true, "profitability_status": "unprofitable"}, "fast_path": {"eligible": false, "reason": null}, "hint": "若未盈利可 calc_cash_runway；非主表主题可 retrieve_context_evidence；否则 submit"}, "duration_ms": 1416}
   ```
4. **`calc_cash_runway`**
   ```json
   {"turn": 4, "arguments": {"reason": "翰思艾泰连续亏损且未盈利，需测算现金跑道以评估融资依赖与资金可持续性"}, "observation": {"ok": true, "cash_burn": {"skipped": false, "reason": null, "CASH_RUNWAY_MONTHS": 20.21, "BURN_RATE_MONTHLY": 7423.75, "END_CASH": 150000.0}}, "duration_ms": 1393}
   ```
5. **`retrieve_context_evidence`**
   ```json
   {"turn": 5, "arguments": {"intent": "financing_dependency", "query": "融資/資金需求/營運資金/所得款項用途/現金消耗", "section_hint": "financial_information,risk_factors,history_and_corporate_structure", "top_k": 5}, "observation": {"ok": true, "doc_id": "hansiaitai", "intent": "financing_dependency", "query": "融資/資金需求/營運資金/所得款項用途/現金消耗", "n": 5, "route": [{"section_id": "financial_information", "section_title": "財務資料", "start_page": 474, "end_page": 507, "confidence": 0.95}, {"section_id": "risk_factors", "section_title": "風險因素", "start_page": 73, "end_page": 126, "confidence": 0.95}, {"section_id": "history_and_corporate_structure", "section_title": "歷史、發展及公司架構", "start_page": 241, "end_page": 276, "confidence": 0.95}], "hits": [{"page": 80, "section_id": "risk_factors", "source_type": "text", "score": 4.386, "matched_terms": ["融資", "資金需求", "營運資金"], "excerpt": "截至2023年及2024年12月31日止年度以及截至2024年及2025年8月31日止八個月，我們經營活動所用現金流量淨額分別為人民幣52.0百萬元、人民幣104.9百萬元、人民幣67.9百萬元及人民幣59.4百萬元。我們的經營活動可能會不"}, {"page": 498, "section_id": "financial_information", "source_type": "text", "score": 4.3818, "matched_terms": ["融資", "資金需求", "營運資金"], "excerpt": "我們的主要現金用途乃為候選藥物的臨床前及臨床開發、行政開支及其他經常性開支提供資金。截至2023年及2024年12月31日止年度以及截至2024年及2025年8月31日止八個月，我們經營活動所用現金流淨額分別為人民幣52.0百萬元、人民幣1"}, {"page": 80, "section_id": "risk_factors", "source_type": "text", "score": 4.3721, "matched_terms": ["融資", "資金需求", "營運資金"], "excerpt": "截至2025年8月31日，我們錄得流動負債淨額人民幣15.2百萬元，此乃主要由於普通股贖回負債人民幣138.5百萬元已入賬為流動負債，而其贖回權將於上市完成前一日自動終止。流動負債淨額狀況可能使我們面臨流動性不足的風險。此進而使我們須尋求充"}, {"page": 502, "section_id": "financial_information", "source_type": "text", "score": 3.3653, "matched_terms": ["融資", "現金消耗"], "excerpt": "展望未來，我們相信我們的流動性需求將通過全球發售所得款項淨額、首次公開發售前投資及轉讓我們於泰州翰中的股權的所得款項予以滿足。截至2025年8月31日，我們的現金及現金等價物為人民幣150.0百萬元。除了可能獲得的銀行借款外，我們於上市前並"}, {"page": 498, "section_id": "financial_information", "source_type": "text", "score": 3.3646, "matched_terms": ["融資", "資金需求"], "excerpt": "我們的管理層密切監控現金及現金結餘的用途，並致力為我們的營運維持穩健的流動資金狀況。展望未來，我們相信全球發售所得款項淨額、來自潛在合作安排的資金以及候選藥物商業化後我們營運所產生的現金將共同滿足我們的流動資金需求。隨著我們業務的不斷擴張，"}], "hint": "完整证据已保存到 state；submit 时引用 page/section/excerpt 即可"}, "duration_ms": 2953}
   ```
6. **`submit_finance_report`**
   ```json
   {"turn": 6, "arguments": {"risk_score": 55, "risk_level": "medium", "reasoning": "翰思艾泰為18A未商業化生物科技公司，連續兩年錄得虧損且虧損擴大（2023年-85.2百萬、2024年-116.9百萬人民幣），無產品收入，OTHER_INCOME僅為其他收入及收益而非產品收入。經營活動現金流持續為負（2024年-104.9百萬），現金消耗主要投向臨床開發與行政開支。截至2025年8月31日現金及現金等價物約150.0百萬元，按月度消耗約7.4百萬元計，現金跑道約20.2個月（落在12-24個月區間）。流動負債淨額-15.2百萬元源於普通股贖回負債（上市前自動終止），流動性依賴全球發售所得款項及股權轉讓。綜合判斷為中等風險。", "summary": "翰思艾泰(18A生物科技)未商業化、連續兩年虧損擴大且經營現金流持續為負，現金跑道約20.2個月，流動性依賴全球發售融資，綜合風險中等（55分）。", "dimensions": [{"dimension": "profitability_growth", "analysis": "連續虧損且虧損擴大：2023年淨虧損-85,160千元、2024年淨虧損-116,922千元人民幣。無產品收入，OTHER_INCOME（其他收入及收益）2023年6,664千元、2024年7,681千元，屬非產品收入，遠不足以覆蓋虧損。研發費用由46,663千元增至74,721千元，行政開支由17,220千元增至46,192千元，支出擴張快於收入，尚未實現盈利，屬18A未商業化階段基線特徵。"}, {"dimension": "cash_flow", "analysis": "經營活動現金流持續為負：2023年-51,994千元、2024年-104,894千元、截至2025年8月止八個月-59,390千元，流出規模持續擴大。截至2025年8月31日現金及現金等價物約150,000千元，按月度消耗約7,424千元計，現金跑道約20.2個月（介於12-24個月），若無後續融資，資金不足以支撐兩年以上持續運營，融資依賴度偏高。"}, {"dimension": "solvency", "analysis": "總負債由2023年266,659千元增至2024年284,867千元及2025年8月299,507千元，淨資產由319,581千元降至144,791千元。截至2025年8月31日錄得流動負債淨額約-15.2百萬元，主要源於普通股贖回負債138.5百萬元入賬為流動負債（其贖回權將於上市完成前一日終止）。整體償債與流動性壓力上升，依賴上市融資緩解。"}, {"dimension": "business_context", "analysis": "屬18A生物科技，尚未商業化，無產品銷售收入，資金主要用於候選藥物臨床前及臨床開發、行政開支及其他經常性開支。現金來源高度依賴全球發售所得款項淨額、首次公開發售前投資及轉讓泰州翰中股權所得款項。候選藥物商業化前的持續虧損屬基線事實，需配合現金跑道與CFO一併衡量其資金可持續性。"}], "score_breakdown": [{"code": "CONTINUOUS_LOSS", "delta": 25, "rule_ref": "連續虧損", "metric_value": "NET_LOSS 2023=-85,160; 2024=-116,922 (人民幣千元)", "evidence_page": 562, "note": "連續兩年虧損且虧損擴大，無產品收入"}, {"code": "CFO_NEGATIVE", "delta": 15, "rule_ref": "經營現金流持續為負", "metric_value": "CFO 2023=-51,994; 2024=-104,894; 2025i=-59,390 (人民幣千元)", "evidence_page": 569, "note": "經營活動現金流持續為負且流出擴大"}, {"code": "CASH_RUNWAY_12_24", "delta": 10, "rule_ref": "現金跑道12-24個月", "metric_value": "現金跑道≈20.2個月；END_CASH=150,000千元", "evidence_page": 502, "note": "現金跑道介於12-24個月，資金可持續性有限"}, {"code": "other_solvency_risk", "delta": 5, "rule_ref": "流動負債淨額風險", "metric_value": "流動負債淨額=-15.2百萬元（普通股贖回負債138.5百萬）", "evidence_page": 80, "note": "截至2025年8月31日流動負債淨額為負，流動性壓力上升"}], "negative_findings": [{"code": "CONTINUOUS_LOSS", "rule_ref": "連續虧損", "description": "連續兩年淨虧損且虧損由-85,160千元擴大至-116,922千元，尚無產品收入"}, {"code": "CFO_NEGATIVE", "rule_ref": "經營現金流為負", "description": "經營活動現金流連續為負且流出規模擴大（2024年-104,894千元）"}, {"code": "CASH_RUNWAY_12_24", "rule_ref": "現金跑道不足", "description": "現金跑道約20.2個月，介於12-24個月，依賴後續融資"}, {"code": "other_solvency_risk", "rule_ref": "流動性風險", "description": "截至2025年8月31日流動負債淨額-15.2百萬元，源於普通股贖回負債"}], "risk_points": [{"code": "CONTINUOUS_LOSS", "level": "high", "rule_ref": "連續虧損", "description": "連續兩年虧損且虧損擴大，未商業化無產品收入", "metric_value": "NET_LOSS 2024=-116,922千元", "evidence_page": 562}, {"code": "CFO_NEGATIVE", "level": "high", "rule_ref": "經營現金流為負", "description": "經營活動現金流持續為負且流出擴大", "metric_value": "CFO 2024=-104,894千元", "evidence_page": 569}, {"code": "CASH_RUNWAY_12_24", "level": "medium", "rule_ref": "現金跑道不足", "description": "現金跑道約20.2個月，需後續融資支撐", "metric_value": "跑道≈20.2個月", "evidence_page": 502}]}, "observation": {"ok": true, "finished": true, "risk_score": 55.0, "risk_level": "medium", "warnings": ["theme_max_anchor:loss:CONTINUOUS_LOSS", "theme_max_anchor:cfo:CFO_NEGATIVE", "theme_runway_anchor:CASH_RUNWAY_12_24:10"], "summary": "翰思艾泰(18A生物科技)未商業化、連續兩年虧損擴大且經營現金流持續為負，現金跑道約20.2個月，流動性依賴全球發售融資，綜合風險中等（55分）。", "rules_floor": {"rules_score": 50.0, "rules_score_deduped": 55.0, "llm_score": 55.0, "final_score": 55.0, "flags": {"continuous_net_loss": true, "latest_full_year_loss": true, "cfo_persistently_negative": true, "gp_margin_drop_gt_5pp": false, "runway_lt_12": false, "runway_12_24": true, "burn_yoy_up_gt_30": false}, "theme_merge": true}, "submit_recovered": false}, "duration_ms": 18880}
   ```

### 2.8 分析结论

- 评分模式 **react+rules_floor**；风险分 **55.0**（medium）。门控：未盈利=`True`，跳过3.4=`False`（None），跳过2.4=`False`（None）。
- 模型 think 状态：`ok`（全文见推理日志 `[model_think]`）。
- 结构化推理摘要：翰思艾泰為18A未商業化生物科技公司，連續兩年錄得虧損且虧損擴大（2023年-85.2百萬、2024年-116.9百萬人民幣），無產品收入，OTHER_INCOME僅為其他收入及收益而非產品收入。經營活動現金流持續為負（2024年-104.9百萬），現金消耗主要投向臨床開發與行政開支。截至2025年8月31日現金及現金等價物約150.0百萬元，按月度消耗約7.4百萬元計，現金跑道約20.2個月（落在12-24個月區間）。流動負債淨額-15.2百萬元源於普通股贖回負債（上市前自動終止），流動性依賴全球發售所得款項及股權轉讓。綜合判斷為中等風險。
- LLM 摘要：翰思艾泰(18A生物科技)未商業化、連續兩年虧損擴大且經營現金流持續為負，現金跑道約20.2個月，流動性依賴全球發售融資，綜合風險中等（55分）。
- 期内利润（NET_LOSS 字段存利润序列，正数=盈利）：2023=-85,160、2024=-116,922。
- 主表证据定位：TBL_IS@p562, TBL_BS@p563, TBL_CF@p569, TBL_BS_COMPANY@p572。
- 推理日志：`/nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/logs/翰思艾泰_finance_20260808_034024.log`

### 2.9 阴性发现（低风险说明）

- **CONTINUOUS_LOSS**（連續虧損）：連續兩年淨虧損且虧損由-85,160千元擴大至-116,922千元，尚無產品收入
- **CFO_NEGATIVE**（經營現金流為負）：經營活動現金流連續為負且流出規模擴大（2024年-104,894千元）
- **CASH_RUNWAY_12_24**（現金跑道不足）：現金跑道約20.2個月，介於12-24個月，依賴後續融資
- **other_solvency_risk**（流動性風險）：截至2025年8月31日流動負債淨額-15.2百萬元，源於普通股贖回負債

## 4. 改进建议

1. **[已做] 财务 LLM 主路径**：retrieve → extract_metrics → gates → analyze_finance(单次四维 LLM) → 可解释评分；规则打分降为 fallback（`--finance-rules-only`）。
2. **[已做] Gemma4 reasoning**：OpenRouter `reasoning.enabled`；日志区分 `[model_think]` / `[structured_reasoning]`。
3. **[已做] 推理日志落盘**：`logs/{doc}_{agent}_{ts}.log` + `.jsonl`（时间/文档/流程/工具skills/过程/结果/推理链）。
4. **[已做] 财务 BS 交叉校验**：若 TOTAL_ASSETS < NET_ASSETS，用 NET+LIAB 回填。
5. **法务检索源**：可用 `--use-live-retrieval`；`--use-llm` 做法务结构化增强。

---

_本报告由 `scripts/generate_analysis_report.py` 根据 Agent 结构化输出自动生成。_
