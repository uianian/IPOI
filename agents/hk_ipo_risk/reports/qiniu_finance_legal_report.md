# 七牛智能 — 财务/法务 Agent 结果分析报告

- 生成时间：2026-07-24 15:25:25
- 招股书：`qiniu.pdf`
- doc_id：`qiniu`
- 参考基本面融合分：`50.55` （legal×0.45 + finance×0.55；总控未启用）
- 财务评分模式：`react`
- 推理日志：`/nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/logs/七牛_finance_20260724_151006.log`
- 说明：reference_fundamental_score = legal*0.45 + finance*0.55; master/cross_agent_features 为本轮占位，总控辩论未启用

## 1. 总览

| Agent | 风险分 (0-100↑风险) | 等级 | 摘要 |
|-------|---------------------|------|------|
| 财务穿透 | **60.0** | medium | 公司持续亏损且现金流承压，虽负债率低但流动性风险中等，依赖IPO募资改善资金状况。 |
| 法务合规 | **39.0** | low | 法务 3.1/3.2/3.3 抽取完成；3.5=跳过；风险分 39.0 (low) |

## 2. 财务穿透 Agent

### 2.1 得分与分解

| 代码 | 加分 | 规则 | 指标值 | 说明 | 证据页 |
|------|------|------|--------|------|--------|
| NET_LOSS_CONTINUOUS | +30.0 | profitability_gate | -324,108.0 | 连续三年亏损，扣分项 | 0 |
| CASH_RUNWAY_LOW | +20.0 | cash_runway_gate | < 12 months | 现金跑道不足12-24个月，扣分项 | 0 |
| REV_VOLATILITY | +10.0 | growth_stability | 14.71亿 $\rightarrow$ 11.47亿 $\rightarrow$ 13.34亿 | 营收波动较大，增长不稳 | 0 |

### 2.2 四维分析（LLM）

#### `profitability_growth` — status=`analyzed`

公司营收在2021-2023年间波动较大（14.71亿 $\rightarrow$ 11.47亿 $\rightarrow$ 13.34亿），且持续处于净亏损状态。2023年净亏损达3.24亿元，2024年（部分期间）亏损1.48亿元。毛利率维持在20%左右，盈利能力尚未改善。


#### `cash_flow` — status=`analyzed`

截至2024年，现金及现金等价物为2.37亿元。参考2023年年度亏损3.24亿元，若亏损额不大幅下降，现金跑道预计不足12个月，流动性压力较大。


#### `solvency` — status=`analyzed`

公司资产负债率极低，2024年总负债仅2,216万元，相对于6.17亿元的总资产，偿债能力极强，无显著债务违约风险。


#### `business_context` — status=`analyzed`

主营MPaaS产品（QCDN, Kodo, Dora），服务于TMT等行业。商业模式依赖于云服务规模效应，但面临激烈的市场竞争及跨境监管风险（Page 71, 102）。资金需求依赖于业务运营、银行借款及IPO募资（Page 439）。



### 2.3 推理链

**[structured_reasoning]**

公司财务状况呈现典型的“低负债、高亏损”特征。虽然资产负债表健康，但利润表持续承压，且现金储备相对于亏损速度而言较为紧张，存在明显的融资依赖和流动性风险。

**[model_think 摘录]**（全文见 logs）

> I have gathered the following information: 1.  **Profitability & Growth**:     - Revenue: 2021 (1.47M), 2022 (1.15M), 2023 (1.33M), 2024 (0.34M - likely partial).     - Net Profit/Loss: Consistently negative. 2021 (-219k), 2022 (-212k), 2023 (-324k), 2024 (-148k).     - GP Margin: Stable around 20%.     - Conclusion: Unprofitable, continuous losses.  2.  **Cash Flow & Solvency**:     - Cash & Equivalents (2024): 236,562.     - Total Liabilities (2024): 22,164.     - Solvency is high (low debt re

### 2.4 门控

```json
{
  "is_unprofitable": true,
  "latest_full_year_loss": true,
  "continuous_net_loss": true,
  "profitability_basis": "NET_LOSS/年內利潤 series; positive=profit",
  "issuer_type": "general",
  "is_biotech_18a": false,
  "skip_3_4": false,
  "skip_3_4_reason": null,
  "skip_2_4": true,
  "skip_2_4_reason": "non-biotech",
  "skip_3_5": true,
  "skip_3_5_reason": "non-biotech"
}
```

### 2.5 抽取指标

| 指标 | 2021 | 2022 | 2023 | 2024 | 2023_i1 | p4 | p5 |
|------|------|------|------|------|------|------|------|
| REV | 1,471,010 | 1,147,290 | 1,333,991 | 342,373 | 270,890 | — | — |
| COGS | -1,179,834 | -918,649 | -1,053,746 | -271,833 | -221,372 | — | — |
| GP | 291,176 | 228,641 | 280,245 | 70,540 | 49,518 | — | — |
| NET_LOSS | -219,706 | -212,752 | -324,108 | -148,022 | -98,329 | — | — |
| TOTAL_ASSETS | 688,776 | 553,290 | 621,974 | 616,578 | — | 148,686 | 144,058 |
| TOTAL_LIAB | 33,216 | 10,301 | 2,845 | 22,164 | — | -2,238,353 | -2,676,178 |
| CASH_EQ | 285,523 | 187,404 | 166,378 | 236,562 | — | — | — |
| CV_PREF | 2,672,314 | 3,006,655 | 3,215,039 | 3,332,247 | — | — | — |
| END_CASH | 337,348 | 290,361 | 274,200 | 273,441 | 302,725 | — | — |
| GP_MARGIN | 19.79 | 19.93 | 21.01 | 20.60 | 18.28 | — | — |

3.4 现金消耗：skipped=`False`，reason=`None`，runway=`None`

### 2.6 召回证据（主表）

| 表/字段 | 页码 | 类型 | 命中数 | 年份列 | 摘录 |
|--------|------|------|--------|--------|------|
| TBL_IS | 500 | table | — | — | 截至12月31日止年度 截至3月31日止三個月 附註 2021年人民幣千元 2022年人民幣千元 2023年人民幣千元 2023年人民幣千元（未經審核） 2024年人民幣千元 收益 5 1,471,010 1,147,290 1,333,991 270,890 342,373 銷售成本 (1,179,834) (918,649) (1,053,746) (221,372) (271,833) 毛… |
| TBL_BS | 502 | table | — | — | 附註 2021年12月31日人民幣千元 2022年12月31日人民幣千元 2023年12月31日人民幣千元 2024年3月31日人民幣千元 非流動資產 物業、廠房及設備 13 231,121 171,811 126,951 118,387 使用權資產 14 43,149 26,113 12,669 33,985 其他無形資產 15 301 – – – 於聯營公司的投資 17 – – – – 按公… |
| TBL_CF | 509 | table | — | — | 截至12月31日止年度 截至3月31日止三個月 附註 2021年人民幣千元 2022年人民幣千元 2023年人民幣千元 2023年人民幣千元（未經審核） 2024年人民幣千元 經營活動所得現金流量 除稅前虧損： (219,706) (212,752) (324,108) (98,329) (148,022) 經調整： 金融資產減值虧損 6 4,763 8,233 11,757 1,893 4,3… |

#### 2.6.1 章节化上下文证据

- intent=`business_model` query=`七牛的商业模式、主要收入来源及成本结构` → business@p236-341, risk_factors@p57-123, summary@p15-34
- intent=`financing_dependency` query=`七牛的融资情况、外部资金依赖及还款压力` → history_and_corporate_structure@p184-235, financial_information@p385-448, risk_factors@p57-123

| 意图章节 | 页码 | 类型 | 分数 | 匹配词 | 摘录 |
|---|---:|---|---:|---|---|
| business | 276 | table | 2.3954 | 商業模式 | <table><tr><td>行業</td><td>• 涉及廣泛的行業，主要包括TMT(技術、媒體及電信)行業的公司，例如短視頻社區、電商平台、科技平台等</td><td>• 涉及廣泛的行業(尤其是經營實體經濟的公司)，包括金融、能源、製造、房地產等</td></tr><tr><td>業務性質</td><td>• 通常為商業模式由廣告流量驅動的公司</td><td>• 通常為正在進行數字化轉型的企業</td></tr><tr><td>規模及於各自行業的地位</td><td>• |
| business | 238 | text | 2.3726 | 商業模式 | 我們的主要產品及服務包括(1) MPaaS產品，即一系列音視頻解決方案，包括加速內容分發的專有內容分發網絡（「QCDN」）、存儲內容的對象存儲平台（「Kodo」）、互動直播產品及智媒數據分析平台（「Dora」），主要服務於開發能力強及具有較強靈活性需求的客戶；以及(2) APaaS解決方案，為基於我們的MPaaS能力及利用我們的低代碼平台的場景化音視頻解決方案，主要旨在使客戶僅需簡易部署，即可快速調用不同功能，實現業務目標。下圖說明我們的商業模式： |
| risk_factors | 71 | text | 2.3589 | 商業模式 | 在若干情況下，遵守一個國家的法律及法規的同時可能會違反另一國家的法律及法規。我們無法向閣下保證我們能夠完全遵守各外國司法權區的法律要求，並成功地使我們的商業模式適應當地市場條件。 |
| business | 250 | text | 1.5507 | — | 我們的業務模式 |
| business | 297 | text | 1.5313 | — | 平均收入貢獻、留存率及收入淨擴展率 |
| financial_information | 439 | text | 3.362 | 融資, 資金需求 | 我們過往主要以業務運營所得款項、銀行借款及發行優先股為我們的現金需求提供資金。全球發售後，我們擬透過業務運營所得現金及銀行借款，連同全球發售所得款項淨額為我們未來的資金需求提供資金。我們預期未來可取得用於撥付營運的融資不會發生任何重大變化。 |
| risk_factors | 102 | text | 2.384 | 融資 | 中國政府部門對人民幣兌換成外幣(以及在若干情況下向中國境外匯款)實施監管。我們以人民幣收取絕大部分淨收益。根據我們目前的公司架構，於開曼群島的本公司依賴間接來自中國附屬公司的股息付款來滿足我們可能出現的任何現金及融資需求。根據現行中國外匯法規，經常項目付款(如盈利分配以及貿易及服務相關外匯交易)可不必取得國家外匯管理局事先批准以外幣進行，惟需符合若干程序規定。因此，我們的中國附屬公司能以外幣向我們支付股息，而毋須取得國家外匯管理局的事先批准，惟需遵守中國外匯監管的若干程序。然 |
| financial_information | 435 | text | 2.3825 | 融資 | 計息銀行及其他借款主要產生自主要用於日常營運及管理現金流的有擔保及無擔保銀行貸款及有擔保借款。於往績記錄期間有關我們從中國的商業銀行借款的貸款協議載有限制我們(其中包括)使用所借資金的標準契約，且在(其中包括)發生合併、收購、分拆、投資合營企業、業務範圍變更、出售或處置重大資產、公司重組、重大外部投資、承擔額外債務融資、重大訴訟或清盤、破產或減少註冊資本時，我們須通知銀行及／或事先取得銀行的書面同意。經我們的董事確認，於往績記錄期間及直至最後實際可行日期，我們並無違反貸款協議 |
| financial_information | 392 | text | 2.3717 | 融資 | 當合約包含一個融資部分，為客戶提供融資轉讓商品或服務超過一年的重大利益時，收益按應收金額的現值計量，使用我們和客戶之間在合約開始時的單獨融資交易中反映的貼現率貼現。當合約包含一個融資部分，為我們提供超過一年的重大財務利益時，根據合約確認的收益包括根據實際利息法對合約負債累積的利息支出。對於客戶付款和轉讓承諾的商品或服務之間的期限為一年或更短的合約，交易價格不因重大融資部分的影響而調整，採用國際財務報告準則第15號中的實用權宜之計。 |
| risk_factors | 84 | text | 2.3664 | 融資 | 我們可能無法及時或以可接受的條款獲得額外資金，或根本無法獲得任何額外資金。此外，我們日後的資金或其他業務需求可能要求我們出售額外的股權或債務證券或獲得信貸融資。出售額外股權或與股權掛鉤的證券可能會攤薄我們股東的股權。任何債務的產生亦將導致債務償還義務增加，並可能導致經營和融資契約而可能限制我們的運營或我們向股東支付股息的能力。 |

### 2.7 工具调用链

- 耗时：`141.587s`

1. **`retrieve_finance`**
   ```json
   {"turn": 1, "arguments": {"reason": "开始财务穿透分析，首先需要检索三张财务主表（资产负债表、利润表、现金流量表）。"}, "observation": {"ok": true, "source": "offline:/nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_qiniu_finance.json", "tables": ["TBL_IS", "TBL_BS", "TBL_CF"], "skipped_fields": 8, "hint": "下一步可调用 extract_metrics"}, "duration_ms": 18236}
   ```
2. **`extract_metrics`**
   ```json
   {"turn": 2, "arguments": {"reason": "已检索到财务主表，现在需要从中抽取标准财务指标（如营收、净利润、现金余额、负债率等）以便进行后续分析。"}, "observation": {"ok": true, "metric_keys": ["REV", "COGS", "GP", "NET_LOSS", "TOTAL_ASSETS", "TOTAL_LIAB", "CASH_EQ", "CV_PREF", "END_CASH", "GP_MARGIN"], "years": ["2021", "2022", "2023", "2024"], "metrics_summary": {"REV": {"2021": 1471010.0, "2022": 1147290.0, "2023": 1333991.0, "2023_i1": 270890.0, "2024": 342373.0}, "GP": {"2021": 291176.0, "2022": 228641.0, "2023": 280245.0, "2023_i1": 49518.0, "2024": 70540.0}, "GP_MARGIN": {"2021": 19.79, "2022": 19.93, "2023": 21.01, "2023_i1": 18.28, "2024": 20.6}, "NET_PROFIT_OR_LOSS": {"2021": -219706.0, "2022": -212752.0, "2023": -324108.0, "2023_i1": -98329.0, "2024": -148022.0}, "CASH_EQ": {"2021": 285523.0, "2022": 187404.0, "2023": 166378.0, "2024": 236562.0}, "TOTAL_ASSETS": {"2021": 688776.0, "2022": 553290.0, "2023": 621974.0, "2024": 616578.0, "p4": 148686.0, "p5": 144058.0}, "TOTAL_LIAB": {"2021": 33216.0, "2022": 10301.0, "2023": 2845.0, "2024": 22164.0, "p4": -2238353.0, "p5": -2676178.0}}, "metric_note": "NET_PROFIT_OR_LOSS 为底线利润/亏损字段；正数=盈利，负数=亏损。", "bs_reconcile": {"changed": false, "note": null}, "hint": "下一步可调用 derive_gates"}, "duration_ms": 3158}
   ```
3. **`derive_gates`**
   ```json
   {"turn": 3, "arguments": {"reason": "已抽取财务指标，现在需要通过 derive_gates 判断公司是否盈利，以及是否需要触发现金跑道（cash runway）计算或 biotech 专项门控。"}, "observation": {"ok": true, "gates": {"is_unprofitable": true, "continuous_net_loss": true, "latest_full_year_loss": true, "skip_3_4": false, "skip_3_4_reason": null, "skip_2_4": true, "issuer_type": "general", "is_biotech_18a": false, "net_series": {"2021": -219706.0, "2022": -212752.0, "2023": -324108.0, "2024": -148022.0}, "profitability_basis": "NET_LOSS/年內利潤 series; positive=profit"}, "fast_path": {"eligible": false, "reason": null}, "hint": "若未盈利可 calc_cash_runway；非主表主题可 retrieve_context_evidence；否则 submit"}, "duration_ms": 18427}
   ```
4. **`calc_cash_runway`**
   ```json
   {"turn": 4, "arguments": {"reason": "公司处于持续亏损状态且未触发 skip_3_4 门控，必须测算现金跑道以评估其生存能力和融资依赖风险。"}, "observation": {"ok": true, "cash_burn": {"skipped": false, "reason": null, "CASH_RUNWAY_MONTHS": null, "BURN_RATE_MONTHLY": null, "END_CASH": 236562.0}}, "duration_ms": 7658}
   ```
5. **`retrieve_context_evidence`**
   ```json
   {"turn": 5, "arguments": {"intent": "business_model", "query": "七牛的商业模式、主要收入来源及成本结构", "reason": "公司持续亏损，需要分析其商业模式是否具有可持续性，以及成本结构是否存在异常。"}, "observation": {"ok": true, "doc_id": "qiniu", "intent": "business_model", "query": "七牛的商业模式、主要收入来源及成本结构", "n": 5, "route": [{"section_id": "business", "section_title": "業務", "start_page": 236, "end_page": 341, "confidence": 0.95}, {"section_id": "risk_factors", "section_title": "風險因素", "start_page": 57, "end_page": 123, "confidence": 0.95}, {"section_id": "summary", "section_title": "概要", "start_page": 15, "end_page": 34, "confidence": 0.95}], "hits": [{"page": 276, "section_id": "business", "source_type": "table", "score": 2.3954, "matched_terms": ["商業模式"], "excerpt": "<table><tr><td>行業</td><td>• 涉及廣泛的行業，主要包括TMT(技術、媒體及電信)行業的公司，例如短視頻社區、電商平台、科技平台等</td><td>• 涉及廣泛的行業(尤其是經營實體經濟的公司)，包括金融、能源、製造"}, {"page": 238, "section_id": "business", "source_type": "text", "score": 2.3726, "matched_terms": ["商業模式"], "excerpt": "我們的主要產品及服務包括(1) MPaaS產品，即一系列音視頻解決方案，包括加速內容分發的專有內容分發網絡（「QCDN」）、存儲內容的對象存儲平台（「Kodo」）、互動直播產品及智媒數據分析平台（「Dora」），主要服務於開發能力強及具有較"}, {"page": 71, "section_id": "risk_factors", "source_type": "text", "score": 2.3589, "matched_terms": ["商業模式"], "excerpt": "在若干情況下，遵守一個國家的法律及法規的同時可能會違反另一國家的法律及法規。我們無法向閣下保證我們能夠完全遵守各外國司法權區的法律要求，並成功地使我們的商業模式適應當地市場條件。"}, {"page": 250, "section_id": "business", "source_type": "text", "score": 1.5507, "matched_terms": [], "excerpt": "我們的業務模式"}, {"page": 297, "section_id": "business", "source_type": "text", "score": 1.5313, "matched_terms": [], "excerpt": "平均收入貢獻、留存率及收入淨擴展率"}], "hint": "完整证据已保存到 state；submit 时引用 page/section/excerpt 即可"}, "duration_ms": 28449}
   ```
6. **`retrieve_context_evidence`**
   ```json
   {"turn": 5, "arguments": {"intent": "financing_dependency", "query": "七牛的融资情况、外部资金依赖及还款压力", "reason": "公司未盈利且现金余额有限，需确认其对外部融资的依赖程度。"}, "observation": {"ok": true, "doc_id": "qiniu", "intent": "financing_dependency", "query": "七牛的融资情况、外部资金依赖及还款压力", "n": 5, "route": [{"section_id": "history_and_corporate_structure", "section_title": "歷史、發展及公司架構", "start_page": 184, "end_page": 235, "confidence": 0.95}, {"section_id": "financial_information", "section_title": "財務資料", "start_page": 385, "end_page": 448, "confidence": 0.95}, {"section_id": "risk_factors", "section_title": "風險因素", "start_page": 57, "end_page": 123, "confidence": 0.95}], "hits": [{"page": 439, "section_id": "financial_information", "source_type": "text", "score": 3.362, "matched_terms": ["融資", "資金需求"], "excerpt": "我們過往主要以業務運營所得款項、銀行借款及發行優先股為我們的現金需求提供資金。全球發售後，我們擬透過業務運營所得現金及銀行借款，連同全球發售所得款項淨額為我們未來的資金需求提供資金。我們預期未來可取得用於撥付營運的融資不會發生任何重大變化。"}, {"page": 102, "section_id": "risk_factors", "source_type": "text", "score": 2.384, "matched_terms": ["融資"], "excerpt": "中國政府部門對人民幣兌換成外幣(以及在若干情況下向中國境外匯款)實施監管。我們以人民幣收取絕大部分淨收益。根據我們目前的公司架構，於開曼群島的本公司依賴間接來自中國附屬公司的股息付款來滿足我們可能出現的任何現金及融資需求。根據現行中國外匯法"}, {"page": 435, "section_id": "financial_information", "source_type": "text", "score": 2.3825, "matched_terms": ["融資"], "excerpt": "計息銀行及其他借款主要產生自主要用於日常營運及管理現金流的有擔保及無擔保銀行貸款及有擔保借款。於往績記錄期間有關我們從中國的商業銀行借款的貸款協議載有限制我們(其中包括)使用所借資金的標準契約，且在(其中包括)發生合併、收購、分拆、投資合營"}, {"page": 392, "section_id": "financial_information", "source_type": "text", "score": 2.3717, "matched_terms": ["融資"], "excerpt": "當合約包含一個融資部分，為客戶提供融資轉讓商品或服務超過一年的重大利益時，收益按應收金額的現值計量，使用我們和客戶之間在合約開始時的單獨融資交易中反映的貼現率貼現。當合約包含一個融資部分，為我們提供超過一年的重大財務利益時，根據合約確認的收"}, {"page": 84, "section_id": "risk_factors", "source_type": "text", "score": 2.3664, "matched_terms": ["融資"], "excerpt": "我們可能無法及時或以可接受的條款獲得額外資金，或根本無法獲得任何額外資金。此外，我們日後的資金或其他業務需求可能要求我們出售額外的股權或債務證券或獲得信貸融資。出售額外股權或與股權掛鉤的證券可能會攤薄我們股東的股權。任何債務的產生亦將導致債"}], "hint": "完整证据已保存到 state；submit 时引用 page/section/excerpt 即可"}, "duration_ms": 28449}
   ```
7. **`submit_finance_report`**
   ```json
   {"turn": 6, "arguments": {"dimensions": [{"analysis": "公司营收在2021-2023年间波动较大（14.71亿 $\\rightarrow$ 11.47亿 $\\rightarrow$ 13.34亿），且持续处于净亏损状态。2023年净亏损达3.24亿元，2024年（部分期间）亏损1.48亿元。毛利率维持在20%左右，盈利能力尚未改善。", "dimension": "profitability_growth"}, {"analysis": "截至2024年，现金及现金等价物为2.37亿元。参考2023年年度亏损3.24亿元，若亏损额不大幅下降，现金跑道预计不足12个月，流动性压力较大。", "dimension": "cash_flow"}, {"analysis": "公司资产负债率极低，2024年总负债仅2,216万元，相对于6.17亿元的总资产，偿债能力极强，无显著债务违约风险。", "dimension": "solvency"}, {"analysis": "主营MPaaS产品（QCDN, Kodo, Dora），服务于TMT等行业。商业模式依赖于云服务规模效应，但面临激烈的市场竞争及跨境监管风险（Page 71, 102）。资金需求依赖于业务运营、银行借款及IPO募资（Page 439）。", "dimension": "business_context"}], "negative_findings": [], "reasoning": "公司财务状况呈现典型的“低负债、高亏损”特征。虽然资产负债表健康，但利润表持续承压，且现金储备相对于亏损速度而言较为紧张，存在明显的融资依赖和流动性风险。", "risk_level": "medium", "risk_points": [{"code": "NET_LOSS_CONTINUOUS", "description": "公司连续三年出现净亏损，且2023年亏损额扩大至3.24亿元。", "evidence_page": 0, "level": "high", "metric_value": "-324,108.0 (2023)", "rule_ref": "profitability_gate"}, {"code": "CASH_RUNWAY_SHORT", "description": "现金余额（2.37亿）不足以覆盖一个完整年度的亏损（参考2023年3.24亿），现金跑道较短。", "evidence_page": 0, "level": "medium", "metric_value": "236,562.0 (Cash) / 324,108.0 (Loss)", "rule_ref": "cash_runway_gate"}], "risk_score": 60, "score_breakdown": [{"code": "NET_LOSS_CONTINUOUS", "delta": 30, "evidence_page": 0, "metric_value": "-324,108.0", "note": "连续三年亏损，扣分项", "rule_ref": "profitability_gate"}, {"code": "CASH_RUNWAY_LOW", "delta": 20, "evidence_page": 0, "metric_value": "< 12 months", "note": "现金跑道不足12-24个月，扣分项", "rule_ref": "cash_runway_gate"}, {"code": "REV_VOLATILITY", "delta": 10, "evidence_page": 0, "metric_value": "14.71亿 $\\rightarrow$ 11.47亿 $\\rightarrow$ 13.34亿", "note": "营收波动较大，增长不稳", "rule_ref": "growth_stability"}], "summary": "公司持续亏损且现金流承压，虽负债率低但流动性风险中等，依赖IPO募资改善资金状况。"}, "observation": {"ok": true, "finished": true, "risk_score": 60.0, "risk_level": "medium", "warnings": [], "summary": "公司持续亏损且现金流承压，虽负债率低但流动性风险中等，依赖IPO募资改善资金状况。"}, "duration_ms": 63926}
   ```

### 2.8 分析结论

- 评分模式 **react**；风险分 **60.0**（medium）。门控：未盈利=`True`，跳过3.4=`False`（None），跳过2.4=`True`（non-biotech）。
- 模型 think 状态：`ok`（全文见推理日志 `[model_think]`）。
- 结构化推理摘要：公司财务状况呈现典型的“低负债、高亏损”特征。虽然资产负债表健康，但利润表持续承压，且现金储备相对于亏损速度而言较为紧张，存在明显的融资依赖和流动性风险。
- LLM 摘要：公司持续亏损且现金流承压，虽负债率低但流动性风险中等，依赖IPO募资改善资金状况。
- 期内利润（NET_LOSS 字段存利润序列，正数=盈利）：2021=-219,706、2022=-212,752、2023=-324,108、2024=-148,022。
- 收入与毛利率：2021–2024 收入 1,471,010→342,373（千元），毛利率 19.79%→20.60%。
- 主表证据定位：TBL_IS@p500, TBL_BS@p502, TBL_CF@p509。
- 推理日志：`/nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/logs/七牛_finance_20260724_151006.log`

## 3. 法务合规 Agent

### 3.1 得分与分解

| 代码 | 加分 | 规则 | 指标值 | 说明 | 证据页 |
|------|------|------|--------|------|--------|
| REDEMPTION_MEDIUM | +12.0 | doc§3.1 | — | — | 517, 562, 563, 591 |
| RELATED_PARTY_DISCLOSURE | +15.0 | doc§3.2 | — | 存在关联交易披露 | 17 |
| CONCENTRATION_DISCLOSURE | +12.0 | doc§3.3 | — | 存在客户/供应商集中度披露 | 14, 72 |

### 3.2 章节特征摘要

| 章节 | exists/skipped | 强度 | 关键字段 |
|------|----------------|------|----------|
| 3.1 | exists=True | high | — |
| 3.2 | exists=True | high | ratio_pct=5.0 |
| 3.3 | exists=True | high | top1_customer_pct=11.3; top5_customer_pct=38.5 |
| 3.4 | exists=None | — | owner=finance |
| 3.5 | skipped=True | — | reason=non-biotech |
| 3.6 | exists=None | — | — |

### 3.3 召回证据明细

| 章节 | 页码 | 类型 | 置信度 | 摘录 |
|------|------|------|--------|------|
| 3.1 | 517 | text | 0.09 | 儘管於2024年3月31日貴集團分別錄得流動負債淨額及負債淨額人民幣3,383,787,000元及人民幣3,164,257,000元，歷史財務資料仍按持續經營基準編製。於2024年3月31日，流動負債淨額及負債淨額主要來自可轉換可贖回優先股（「優先股」），金額為人民幣3,332,247,000元。貴公司董事認為，由於相關贖回權將被終止，且該等金融工具將於貴公司股份在聯交所上市後不可撤銷地轉換為股權 |
| 3.1 | 563 | text | 0.07 | 於2023年6月26日，貴集團與A系列至F系列優先股持有人簽訂協議終止附於可轉換可贖回優先股的贖回權。儘管上文所述，貴公司同意倘(i)於香港聯合交易所有限公司的首次公開發售（「香港首次公開發售」）於2025年1月1日或之前尚未完成；(ii)貴公司正式撤回香港首次公開發售的A1備案；(iii)香港首次公開發售的A1備案被香港聯合交易所有限公司拒絕；或(iv)香港首次公開發售的A1備案失效及之後四個月 |
| 3.1 | 563 | text | 0.07 | 於2021年及2022年12月31日，可轉換可贖回優先股被分類為流動負債，是由於優先股持有人可於12個月內要求貴公司贖回其優先股或將可轉換可贖回優先股轉換為普通股。於2023年12月31日及2024年3月31日，可轉換可贖回優先股分類為流動負債，是由於優先股持有人可於12個月內將可轉換可贖回優先股轉換為普通股，即使貴公司可於2023年12月31日及2024年3月31日起計最少十二個月內延遲結算因贖 |
| 3.1 | 562 | text | 0.07 | 於發生以下事項後(以較早發生者為準)：(i)A系列優先股持有人決定行使贖回權(A系列優先股持有人有權於2016年6月30日開始隨時要求貴公司贖回全部當時已發行但尚未流通的股份)，或(ii)未經董事會批准(包括優先股的所有董事投贊成票)，若干合約安排已終止，優先股投資者隨時有權要求貴公司贖回彼等的投資。 |
| 3.1 | 591 | text | 0.07 | * 該金額指贖回可轉換可贖回優先股的價格。於2023年12月31日及2024年3月31日，可轉換可贖回優先股的到期日介乎1年至5年之間，原因是倘若某些贖回權已行使，貴公司可將贖回可轉換可贖回優先股所產生的負債結算延遲至少十二個月。 |
| 3.2 | 17 | text | 0.07 | 此外，為按照中國適用法律及法規開展相關業務，我們的全資附屬公司上海空山已與七牛信息、北京空山、七牛深圳及登記股東簽訂合約安排。鑑於登記股東（即許先生及呂先生）為本公司之關連人士，合約安排項下擬進行的交易將於上市後構成本公司的持續關連交易。 |
| 3.2 | 17 | text | 0.05 | 持續關連交易 |
| 3.2 | 17 | text | 0.05 | 詳情請參閱本招股章程「持續關連交易」。 |
| 3.2 | 17 | text | 0.07 | 此外，為按照中國適用法律及法規開展相關業務，我們的全資附屬公司上海空山已與七牛信息、北京空山、七牛深圳及登記股東簽訂合約安排。鑑於登記股東（即許先生及呂先生）為本公司之關連人士，合約安排項下擬進行的交易將於上市後構成本公司的持續關連交易。 |
| 3.2 | 17 | text | 0.05 | 持續關連交易 |
| 3.3 | 14 | table | 0.04 | 我們的客戶基礎廣泛，遍佈各行各業，包括泛娛樂、社交網絡、醫療、電子商務、教育、媒體、金融服務、汽車、電信和智能製造等。截至2023年12月31日止三個年度以及截至2024年3月31日止三個月，我們來自最大客戶的收益分別佔我們於同期收益的11.3%、8.1%、11.8%及16.1%。於往績記錄期間各年度／期間，我們來自五大客戶的收益分別佔我們同期收益的22.7%、25.5%、34.3%及38.5%。 |
| 3.3 | 14 | table | 0.04 | 我們的供應商主要包括雲技術行業中提供(i)網絡及帶寬服務、(ii)IDC服務及(iii)服務器及存儲服務的企業。截至2023年12月31日止三個年度以及截至2024年3月31日止三個月，與最大供應商的交易金額分別佔該等期間我們採購總額的36.1%、16.3%、5.9%及8.0%。於往績記錄期間之各年度／期間，與五大供應商的交易金額分別佔我們同期採購總額的63.5%、52.4%、25.7%及28.6 |
| 3.3 | 14 | table | 0.04 | 我們的客戶基礎廣泛，遍佈各行各業，包括泛娛樂、社交網絡、醫療、電子商務、教育、媒體、金融服務、汽車、電信和智能製造等。截至2023年12月31日止三個年度以及截至2024年3月31日止三個月，我們來自最大客戶的收益分別佔我們於同期收益的11.3%、8.1%、11.8%及16.1%。於往績記錄期間各年度／期間，我們來自五大客戶的收益分別佔我們同期收益的22.7%、25.5%、34.3%及38.5%。 |
| 3.3 | 14 | table | 0.04 | 我們的供應商主要包括雲技術行業中提供(i)網絡及帶寬服務、(ii)IDC服務及(iii)服務器及存儲服務的企業。截至2023年12月31日止三個年度以及截至2024年3月31日止三個月，與最大供應商的交易金額分別佔該等期間我們採購總額的36.1%、16.3%、5.9%及8.0%。於往績記錄期間之各年度／期間，與五大供應商的交易金額分別佔我們同期採購總額的63.5%、52.4%、25.7%及28.6 |
| 3.3 | 72 | table | 0.02 | 我們未來的成功取決於與眾多客戶建立並保持成功的關係。往績記錄期間，我們受一定程度的集中風險規限，是由於我們的大部分收入來自對主要客戶的銷售。於2021年、2022年及2023年各年以及截至2024年3月31日止三個月，五大客戶分別佔我們之各年度收入的約22.7%、25.5%、34.3%及38.5%。同期，我們的最大客戶佔我們各年度收入的約11.3%、8.1%、11.8%及16.1%。此外，往績記錄 |
| 3.5 | — | — | — | （已跳过：non-biotech） |

### 3.4 计分证据（score_breakdown）

#### `REDEMPTION_MEDIUM`（+12.0，doc§3.1）

- p517（text）：儘管於2024年3月31日貴集團分別錄得流動負債淨額及負債淨額人民幣3,383,787,000元及人民幣3,164,257,000元，歷史財務資料仍按持續經營基準編製。於2024年3月31日，流動負債淨額及負債淨額主要來自可轉換可贖回優先股（「優先股」），金額為人民幣3,332,247,000元。貴公司董事認為，由於相關贖回權將被終止，且該等金融工具將於貴公司股份在聯交所上市後不可撤銷地轉換為股權
- p563（text）：於2023年6月26日，貴集團與A系列至F系列優先股持有人簽訂協議終止附於可轉換可贖回優先股的贖回權。儘管上文所述，貴公司同意倘(i)於香港聯合交易所有限公司的首次公開發售（「香港首次公開發售」）於2025年1月1日或之前尚未完成；(ii)貴公司正式撤回香港首次公開發售的A1備案；(iii)香港首次公開發售的A1備案被香港聯合交易所有限公司拒絕；或(iv)香港首次公開發售的A1備案失效及之後四個月
- p563（text）：於2021年及2022年12月31日，可轉換可贖回優先股被分類為流動負債，是由於優先股持有人可於12個月內要求貴公司贖回其優先股或將可轉換可贖回優先股轉換為普通股。於2023年12月31日及2024年3月31日，可轉換可贖回優先股分類為流動負債，是由於優先股持有人可於12個月內將可轉換可贖回優先股轉換為普通股，即使貴公司可於2023年12月31日及2024年3月31日起計最少十二個月內延遲結算因贖
- p562（text）：於發生以下事項後(以較早發生者為準)：(i)A系列優先股持有人決定行使贖回權(A系列優先股持有人有權於2016年6月30日開始隨時要求貴公司贖回全部當時已發行但尚未流通的股份)，或(ii)未經董事會批准(包括優先股的所有董事投贊成票)，若干合約安排已終止，優先股投資者隨時有權要求貴公司贖回彼等的投資。
- p591（text）：* 該金額指贖回可轉換可贖回優先股的價格。於2023年12月31日及2024年3月31日，可轉換可贖回優先股的到期日介乎1年至5年之間，原因是倘若某些贖回權已行使，貴公司可將贖回可轉換可贖回優先股所產生的負債結算延遲至少十二個月。

#### `RELATED_PARTY_DISCLOSURE`（+15.0，doc§3.2）

存在关联交易披露

- p17（text）：此外，為按照中國適用法律及法規開展相關業務，我們的全資附屬公司上海空山已與七牛信息、北京空山、七牛深圳及登記股東簽訂合約安排。鑑於登記股東（即許先生及呂先生）為本公司之關連人士，合約安排項下擬進行的交易將於上市後構成本公司的持續關連交易。
- p17（text）：持續關連交易
- p17（text）：詳情請參閱本招股章程「持續關連交易」。
- p17（text）：此外，為按照中國適用法律及法規開展相關業務，我們的全資附屬公司上海空山已與七牛信息、北京空山、七牛深圳及登記股東簽訂合約安排。鑑於登記股東（即許先生及呂先生）為本公司之關連人士，合約安排項下擬進行的交易將於上市後構成本公司的持續關連交易。
- p17（text）：持續關連交易

#### `CONCENTRATION_DISCLOSURE`（+12.0，doc§3.3）

存在客户/供应商集中度披露

- p14（table）：我們的客戶基礎廣泛，遍佈各行各業，包括泛娛樂、社交網絡、醫療、電子商務、教育、媒體、金融服務、汽車、電信和智能製造等。截至2023年12月31日止三個年度以及截至2024年3月31日止三個月，我們來自最大客戶的收益分別佔我們於同期收益的11.3%、8.1%、11.8%及16.1%。於往績記錄期間各年度／期間，我們來自五大客戶的收益分別佔我們同期收益的22.7%、25.5%、34.3%及38.5%。
- p14（table）：我們的供應商主要包括雲技術行業中提供(i)網絡及帶寬服務、(ii)IDC服務及(iii)服務器及存儲服務的企業。截至2023年12月31日止三個年度以及截至2024年3月31日止三個月，與最大供應商的交易金額分別佔該等期間我們採購總額的36.1%、16.3%、5.9%及8.0%。於往績記錄期間之各年度／期間，與五大供應商的交易金額分別佔我們同期採購總額的63.5%、52.4%、25.7%及28.6
- p14（table）：我們的客戶基礎廣泛，遍佈各行各業，包括泛娛樂、社交網絡、醫療、電子商務、教育、媒體、金融服務、汽車、電信和智能製造等。截至2023年12月31日止三個年度以及截至2024年3月31日止三個月，我們來自最大客戶的收益分別佔我們於同期收益的11.3%、8.1%、11.8%及16.1%。於往績記錄期間各年度／期間，我們來自五大客戶的收益分別佔我們同期收益的22.7%、25.5%、34.3%及38.5%。
- p14（table）：我們的供應商主要包括雲技術行業中提供(i)網絡及帶寬服務、(ii)IDC服務及(iii)服務器及存儲服務的企業。截至2023年12月31日止三個年度以及截至2024年3月31日止三個月，與最大供應商的交易金額分別佔該等期間我們採購總額的36.1%、16.3%、5.9%及8.0%。於往績記錄期間之各年度／期間，與五大供應商的交易金額分別佔我們同期採購總額的63.5%、52.4%、25.7%及28.6
- p72（table）：我們未來的成功取決於與眾多客戶建立並保持成功的關係。往績記錄期間，我們受一定程度的集中風險規限，是由於我們的大部分收入來自對主要客戶的銷售。於2021年、2022年及2023年各年以及截至2024年3月31日止三個月，五大客戶分別佔我們之各年度收入的約22.7%、25.5%、34.3%及38.5%。同期，我們的最大客戶佔我們各年度收入的約11.3%、8.1%、11.8%及16.1%。此外，往績記錄

### 3.5 工具调用链

- 耗时：`3.208s`

1. **`retrieve_legal`**
   ```json
   {"source": "offline:/nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_qiniu_legal.json", "fields": ["REDEMPTION_CLAUSE", "RELATED_PARTY", "CONCENTRATION", "CASH_BURN_PRESSURE", "PRE_IPO_VALUATION"], "per_query": 5, "has_evidence_by_field": true, "hint": null}
   ```
2. **`parse_grep`**
   ```json
   {"path": "/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/qiniu/full_parse.json", "hits": 0, "pages": []}
   ```
3. **`retrieve_section_evidence`**
   ```json
   {"intents": {"redemption": {"hits": 8, "pages": [204, 205, 186, 68, 68, 204, 68, 194], "route": [{"section_id": "history_and_corporate_structure", "section_title": "歷史、發展及公司架構", "start_page": 184, "end_page": 235, "confidence": 0.95}, {"section_id": "risk_factors", "section_title": "風險因素", "start_page": 57, "end_page": 123, "confidence": 0.95}]}, "related_party": {"hits": 8, "pages": [363, 356, 357, 359, 356, 366, 363, 318], "route": [{"section_id": "connected_transactions", "section_title": "持續關連交易", "start_page": 356, "end_page": 369, "confidence": 0.95}, {"section_id": "business", "section_title": "業務", "start_page": 236, "end_page": 341, "confidence": 0.95}, {"section_id": "financial_information", "section_title": "財務資料", "start_page": 385, "end_page": 448, "confidence": 0.95}]}, "concentration": {"hits": 8, "pages": [283, 426, 306, 72, 73, 312, 319, 320], "route": [{"section_id": "business", "section_title": "業務", "start_page": 236, "end_page": 341, "confidence": 0.95}, {"section_id": "risk_factors", "section_title": "風險因素", "start_page": 57, "end_page": 123, "confidence": 0.95}, {"section_id": "financial_information", "section_title": "財務資料", "start_page": 385, "end_page": 448, "confidence": 0.95}]}}}
   ```
4. **`extract_legal`**
   ```json
   {"sections": {"3.1": {"exists": true, "skipped": null, "evidence_n": 5, "search_log": {"keywords_tried": ["赎回", "贖回", "对赌", "對賭", "回购", "回購", "优先股", "優先股", "领售", "領售", "撤资", "撤資", "贖回權", "可換股", "可转换可赎回", "可轉換可贖回", "股东协议", "股東協議", "特别权利", "特別權利", "赎回权终止", "特別權利終止"], "pages_scanned": [68, 186, 194, 204, 205, 440, 517, 562, 563, 564, 591], "raw_hits": 22, "filtered_noise": 0, "strong_hits": 22, "note": "命中对赌/赎回相关披露"}, "top1_supplier_pct": null, "top5_supplier_pct": null}, "3.2": {"exists": true, "skipped": null, "evidence_n": 5, "search_log": null, "top1_supplier_pct": null, "top5_supplier_pct": null}, "3.3": {"exists": true, "skipped": null, "evidence_n": 5, "search_log": null, "top1_supplier_pct": 36.1, "top5_supplier_pct": 36.1}, "3.5": {"exists": null, "skipped": true, "evidence_n": 0, "search_log": null, "top1_supplier_pct": null, "top5_supplier_pct": null}}}
   ```
5. **`score_legal`**
   ```json
   {"risk_score": 39.0, "breakdown_n": 3}
   ```

### 3.6 分析结论

- 风险分 **39.0**（low）。打分来自披露基础分或规则命中（见 score_breakdown）。
- 3.1 对赌/赎回：exists=`True`，证据强度=`high`
- 3.2 关联交易：exists=`True`，占比=`5.0`。
- 3.3 集中度：exists=`True`，证据页=[14, 14, 14, 14, 72]。
- 3.5 管线风险按 non-biotech 正确跳过。

## 4. 改进建议

1. **[已做] 财务 LLM 主路径**：retrieve → extract_metrics → gates → analyze_finance(单次四维 LLM) → 可解释评分；规则打分降为 fallback（`--finance-rules-only`）。
2. **[已做] Gemma4 reasoning**：OpenRouter `reasoning.enabled`；日志区分 `[model_think]` / `[structured_reasoning]`。
3. **[已做] 推理日志落盘**：`logs/{doc}_{agent}_{ts}.log` + `.jsonl`（时间/文档/流程/工具skills/过程/结果/推理链）。
4. **[已做] 财务 BS 交叉校验**：若 TOTAL_ASSETS < NET_ASSETS，用 NET+LIAB 回填。
5. **法务检索源**：可用 `--use-live-retrieval`；`--use-llm` 做法务结构化增强。

---

_本报告由 `scripts/generate_analysis_report.py` 根据 Agent 结构化输出自动生成。_
