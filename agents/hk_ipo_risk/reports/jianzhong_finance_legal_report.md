# 建中建設 — 财务/法务 Agent 结果分析报告

- 生成时间：2026-07-26 18:05:10
- 招股书：`00589_28-02-2020_建中建設_股份發售.pdf`
- doc_id：`jianzhong`
- 参考基本面融合分：`22.5` （legal×0.45 + finance×0.55；总控未启用）
- 财务评分模式：`react+rules_floor`
- 推理日志：`/nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/logs/建中建設_finance_20260726_180446.log`
- 说明：reference_fundamental_score = legal*0.45 + finance*0.55; master/cross_agent_features 为本轮占位，总控辩论未启用

## 1. 总览

| Agent | 风险分 (0-100↑风险) | 等级 | 摘要 |
|-------|---------------------|------|------|
| 财务穿透 | **0.0** | very_low | 建中建設财务状况稳健，盈利能力强，营收与利润高速增长，无显著财务风险。 |
| 法务合规 | **50.0** | medium | 法务 3.1/3.2/3.3 抽取完成；3.5=跳过；风险分 50.0 (medium) |

## 2. 财务穿透 Agent

### 2.1 得分与分解

_无扣分项（未触发风险规则，或证据不足未计分）_

### 2.2 四维分析（LLM）

#### `profitability_growth` — status=`analyzed`

公司营收规模增长迅速，2016年至2018年从1.57亿元增长至11.93亿元；净利润同步大幅增长，2018年达到1.40亿元，盈利能力强且增长势头明显。


#### `cash_flow` — status=`analyzed`

经营活动现金流（CFO）在完整年度均保持正值，2018年为6,783.8万元，现金及现金等价物余额充足，资金周转状况良好。


#### `solvency` — status=`analyzed`

净资产规模持续扩大，2019年第一季度已达7.80亿元，资产结构稳健，偿债能力较强。


#### `business_context` — status=`analyzed`

未调用 retrieve_context_evidence 检索具体商业模式细节，证据较弱，标为 skipped。



### 2.3 推理链

**[structured_reasoning]**

发行人处于盈利状态且营收、利润高速增长，现金流充足，各项财务指标健康，无明显财务风险点。

**[model_think 摘录]**（全文见 logs）

> The issuer "建中建設" is profitable (`is_unprofitable: false`, `skip_3_4: true`). - Revenue (REV) grew significantly from 2016 to 2018 (156k -> 498k -> 1.19M). - Net Profit (NET_PROFIT_OR_LOSS) grew from 16.9k to 140.5k. - GP Margin is stable around 23-26%. - CFO is generally positive (though 2018_i1 was negative, the full year 2018 was positive at 67.8k). - Cash and Net Assets are increasing.  Since the company is profitable and the financial indicators are healthy, I can proceed to submit the repo

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

| 指标 | 2016 | 2017 | 2018 | 2018_i1 | 2019_i1 |
|------|------|------|------|------|------|
| REV | 156,754 | 498,857 | 1,192,750 | 854,110 | 1,229,737 |
| OTHER_INCOME | 336.00 | 812.00 | 1,762 | 136.00 | 3,007 |
| COGS | -118,618 | -368,999 | -907,228 | -665,600 | -946,889 |
| GP | 38,136 | 129,858 | 285,522 | 188,510 | 282,848 |
| SGA | -12,441 | -25,655 | -80,820 | -58,951 | -77,077 |
| NET_LOSS | 16,912 | 67,549 | 140,494 | 77,614 | 134,995 |
| NET_ASSETS | 55,345 | 312,894 | 556,988 | — | 779,882 |
| CASH_EQ | 3,751 | 2,009 | 93,772 | — | 72,506 |
| CFO | 60,369 | 5,588 | 67,838 | -20,134 | 61,483 |
| CFI | -80,569 | -201,313 | -90,106 | -84,333 | -71,133 |
| GP_MARGIN | 24.33 | 26.03 | 23.94 | 22.07 | 23.00 |

3.4 现金消耗：skipped=`True`，reason=`profitable`，runway=`None`

### 2.6 召回证据（主表）

| 表/字段 | 页码 | 类型 | 命中数 | 年份列 | 摘录 |
|--------|------|------|--------|--------|------|
| TBL_IS | 422 | table | — | — | 附註 截至12月31日止年度 截至9月30日止九個月 2016年人民幣千元 2017年人民幣千元 2018年人民幣千元 2018年人民幣千元（未經審核） 2019年人民幣千元 收益 4 156,754 498,857 1,192,750 854,110 1,229,737 銷售成本 (118,618) (368,999) (907,228) (665,600) (946,889) 毛利 38,1… |
| TBL_BS | 423 | table | — | — | 附註 於12月31日 於9月30日 2016年人民幣千元 2017年人民幣千元 2018年人民幣千元 2019年人民幣千元 非流動資產 物業、廠房及設備 11 209,577 408,801 423,285 407,956 無形資產 12 26 570 793 750 服務特許權安排項下的應收款項 17 – – 36,753 33,861 遞延稅項資產 23(b) 1,871 8,735 1,6… |
| TBL_CF | 427 | table | — | — | 附註 截至12月31日止年度 截至9月30日止九個月 2016年人民幣千元 2017年人民幣千元 2018年人民幣千元 2018年人民幣千元（未經審核） 2019年人民幣千元 經營活動 經營產生／(所用)的現金． 19(b) 61,678 14,219 86,317 (1,883) 99,769 已付所得稅．．．．．．．． (1,309) (8,631) (18,479) (18,251) (3… |
| TBL_BS_COMPANY | 424 | text | — | — | 於2019年9月30日 人民幣千元 非流動資產 於附屬公司之投資 …… 1 …… -* 流動資產 預付款項及其他應收款項 …… 5,027 現金及現金等價物 …… 361 流動負債 應付一間附屬公司之款項 …… 5,027 應付關聯方款項 …… 720 其他應付款項 …… 208 流動負債淨額 …… (567) 負債淨額 …… (567) 資本及儲備 股本 …… 25(b) …… -* 儲備 …… |

#### 2.6.1 章节化上下文证据

_本次未调用章节化上下文检索，或未命中证据。_

### 2.7 工具调用链

- 耗时：`24.379s`

1. **`retrieve_finance`**
   ```json
   {"turn": 1, "arguments": {"reason": "开始财务穿透分析，首先需要检索三张财务主表以获取基础数据。"}, "observation": {"ok": true, "source": "offline:/nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_jianzhong_finance.json", "tables": ["TBL_IS", "TBL_BS", "TBL_BS_COMPANY", "TBL_CF"], "skipped_fields": 8, "hint": "下一步可调用 extract_metrics"}, "duration_ms": 7926}
   ```
2. **`extract_metrics`**
   ```json
   {"turn": 2, "arguments": {"reason": "从检索到的财务主表中抽取标准指标，用于后续的门控计算和风险评估。"}, "observation": {"ok": true, "metric_keys": ["REV", "OTHER_INCOME", "COGS", "GP", "SGA", "NET_LOSS", "NET_ASSETS", "CASH_EQ", "CFO", "CFI", "GP_MARGIN"], "years": ["2016", "2017", "2018"], "metrics_summary": {"REV": {"2016": 156754.0, "2017": 498857.0, "2018": 1192750.0, "2018_i1": 854110.0, "2019_i1": 1229737.0}, "OTHER_INCOME": {"2016": 336.0, "2017": 812.0, "2018": 1762.0, "2018_i1": 136.0, "2019_i1": 3007.0}, "GP": {"2016": 38136.0, "2017": 129858.0, "2018": 285522.0, "2018_i1": 188510.0, "2019_i1": 282848.0}, "GP_MARGIN": {"2016": 24.33, "2017": 26.03, "2018": 23.94, "2018_i1": 22.07, "2019_i1": 23.0}, "NET_PROFIT_OR_LOSS": {"2016": 16912.0, "2017": 67549.0, "2018": 140494.0, "2018_i1": 77614.0, "2019_i1": 134995.0}, "CFO": {"2016": 60369.0, "2017": 5588.0, "2018": 67838.0, "2018_i1": -20134.0, "2019_i1": 61483.0}, "CASH_EQ": {"2016": 3751.0, "2017": 2009.0, "2018": 93772.0, "2019_i1": 72506.0}, "NET_ASSETS": {"2016": 55345.0, "2017": 312894.0, "2018": 556988.0, "2019_i1": 779882.0}}, "metric_note": "NET_PROFIT_OR_LOSS 为底线利润/亏损字段；正数=盈利，负数=亏损。", "bs_reconcile": {"changed": false, "note": null}, "hint": "下一步可调用 derive_gates"}, "duration_ms": 2175}
   ```
3. **`derive_gates`**
   ```json
   {"turn": 3, "arguments": {"reason": "根据提取的指标计算盈利门控和现金跑道门控，确定是否需要进一步分析现金流风险。"}, "observation": {"ok": true, "gates": {"is_unprofitable": false, "continuous_net_loss": false, "latest_full_year_loss": false, "skip_3_4": true, "skip_3_4_reason": "profitable", "skip_2_4": true, "issuer_type": "general", "is_biotech_18a": false, "net_series": {"2016": 16912.0, "2017": 67549.0, "2018": 140494.0}, "profitability_basis": "NET_LOSS/年內利潤 series; positive=profit", "profitability_known": true, "profitability_status": "profitable"}, "fast_path": {"eligible": false, "reason": null}, "hint": "若未盈利可 calc_cash_runway；非主表主题可 retrieve_context_evidence；否则 submit"}, "duration_ms": 3122}
   ```
4. **`submit_finance_report`**
   ```json
   {"turn": 4, "arguments": {"dimensions": [{"analysis": "公司营收规模增长迅速，2016年至2018年从1.57亿元增长至11.93亿元；净利润同步大幅增长，2018年达到1.40亿元，盈利能力强且增长势头明显。", "dimension": "profitability_growth"}, {"analysis": "经营活动现金流（CFO）在完整年度均保持正值，2018年为6,783.8万元，现金及现金等价物余额充足，资金周转状况良好。", "dimension": "cash_flow"}, {"analysis": "净资产规模持续扩大，2019年第一季度已达7.80亿元，资产结构稳健，偿债能力较强。", "dimension": "solvency"}, {"analysis": "未调用 retrieve_context_evidence 检索具体商业模式细节，证据较弱，标为 skipped。", "dimension": "business_context"}], "negative_findings": [], "reasoning": "发行人处于盈利状态且营收、利润高速增长，现金流充足，各项财务指标健康，无明显财务风险点。", "risk_level": "very_low", "risk_score": 0, "score_breakdown": [], "summary": "建中建設财务状况稳健，盈利能力强，营收与利润高速增长，无显著财务风险。"}, "observation": {"ok": true, "finished": true, "risk_score": 0.0, "risk_level": "very_low", "warnings": [], "summary": "建中建設财务状况稳健，盈利能力强，营收与利润高速增长，无显著财务风险。", "rules_floor": {"rules_score": 0.0, "rules_score_deduped": 0, "llm_score": 0.0, "final_score": 0.0, "flags": {"continuous_net_loss": false, "latest_full_year_loss": false, "cfo_persistently_negative": false, "gp_margin_drop_gt_5pp": false, "runway_lt_12": false, "runway_12_24": false, "burn_yoy_up_gt_30": false}}}, "duration_ms": 11088}
   ```

### 2.8 分析结论

- 评分模式 **react+rules_floor**；风险分 **0.0**（very_low）。门控：未盈利=`False`，跳过3.4=`True`（profitable），跳过2.4=`True`（non-biotech）。
- 模型 think 状态：`ok`（全文见推理日志 `[model_think]`）。
- 结构化推理摘要：发行人处于盈利状态且营收、利润高速增长，现金流充足，各项财务指标健康，无明显财务风险点。
- LLM 摘要：建中建設财务状况稳健，盈利能力强，营收与利润高速增长，无显著财务风险。
- 期内利润（NET_LOSS 字段存利润序列，正数=盈利）：2016=16,912、2017=67,549、2018=140,494。
- 收入与毛利率：2016–2018 收入 156,754→1,192,750（千元），毛利率 24.33%→23.94%。
- 主表证据定位：TBL_IS@p422, TBL_BS@p423, TBL_CF@p427, TBL_BS_COMPANY@p424。
- 推理日志：`/nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/logs/建中建設_finance_20260726_180446.log`

## 3. 法务合规 Agent

### 3.1 得分与分解

| 代码 | 加分 | 规则 | 指标值 | 说明 | 证据页 |
|------|------|------|--------|------|--------|
| RELATED_PARTY_HIGH | +25.0 | doc§3.2 | — | — | 42, 226, 359 |
| CONCENTRATION_HIGH | +25.0 | doc§3.3 | — | — | 13, 475 |

### 3.2 章节特征摘要

| 章节 | exists/skipped | 强度 | 关键字段 |
|------|----------------|------|----------|
| 3.1 | exists=False | low | — |
| 3.2 | exists=True | high | ratio_pct=95.0 |
| 3.3 | exists=True | high | top1_customer_pct=99.5; top5_customer_pct=99.5 |
| 3.4 | exists=None | — | owner=finance |
| 3.5 | skipped=True | — | reason=non-biotech |
| 3.6 | exists=None | — | — |

### 3.3 召回证据明细

| 章节 | 页码 | 类型 | 置信度 | 摘录 |
|------|------|------|--------|------|
| 3.1 | — | — | — | 未召回强证据 / 判定不存在 |
| 3.2 | 42 | text | 0.04 | 於本招股章程中，除文義另有所指外，否則「聯繫人」、「緊密聯繫人」、「關連人士」、「關連交易」、「控股股東」、「核心關連人士」、「附屬公司」及「主要股東」等詞彙均具有上市規則所賦予的涵義。 |
| 3.2 | 226 | table | 0.03 | 福建潤江95.0%的股權由本公司執行董事兼董事長、控股股東荀名紅先生持有。由於荀名紅先生持有福建潤江超過30.0%的股權，根據上市規則第14A章，福建潤江被視為荀名紅先生的聯繫人及本公司的關連人士。進一步詳情請參閱「關連交易」。福建潤江為一間投資控股公司。 |
| 3.2 | 359 | text | 0.03 | (ii)該等關聯方交易不會致使本集團往績記錄期間的經營業績失真或導致本集團的過往業績不能反映本集團的未來表現；(iii)除「關連交易」所披露的關連交易外，所有其他關聯方交易將於上市後終止；及(iv)所有與關聯方的非貿易結餘將於上市前結清。 |
| 3.2 | 42 | text | 0.04 | 於本招股章程中，除文義另有所指外，否則「聯繫人」、「緊密聯繫人」、「關連人士」、「關連交易」、「控股股東」、「核心關連人士」、「附屬公司」及「主要股東」等詞彙均具有上市規則所賦予的涵義。 |
| 3.2 | 226 | table | 0.03 | 福建潤江95.0%的股權由本公司執行董事兼董事長、控股股東荀名紅先生持有。由於荀名紅先生持有福建潤江超過30.0%的股權，根據上市規則第14A章，福建潤江被視為荀名紅先生的聯繫人及本公司的關連人士。進一步詳情請參閱「關連交易」。福建潤江為一間投資控股公司。 |
| 3.3 | 13 | table | 0.07 | 我們的供應商主要包括混凝土、樁、鋼筋及木材模板等材料供應商。截至2018年12月31止三個年度各年及截至2019年9月30日止九個月，我們的五大供應商分別合共佔我們材料採購總額的約55.3%、38.6%、35.7%及32.0%，而我們的最大供應商於各年度／期間分別佔我們同期材料採購總額的約16.8%、11.6%、12.1%及13.1%。於往績記錄期間，我們亦按項目基準委聘分包商(主要包括勞務分包商 |
| 3.3 | 13 | table | 0.07 | 我們的供應商主要包括混凝土、樁、鋼筋及木材模板等材料供應商。截至2018年12月31止三個年度各年及截至2019年9月30日止九個月，我們的五大供應商分別合共佔我們材料採購總額的約55.3%、38.6%、35.7%及32.0%，而我們的最大供應商於各年度／期間分別佔我們同期材料採購總額的約16.8%、11.6%、12.1%及13.1%。於往績記錄期間，我們亦按項目基準委聘分包商(主要包括勞務分包商 |
| 3.3 | 475 | table | 0.08 | 貴集團的信貸風險主要受每名客戶的個別特徵而非客戶業務所在行業的影響，因此，貴集團主要在面臨個別客戶帶來的重大風險時產生高度集中的信貸風險。於2016年、2017年及2018年12月31日以及2019年9月30日，77.9%、66.1%、53.1%及65.8%的貿易應收款項總額及合約資產來自貴集團最大客戶，99.5%、85.6%、79.2%及87.2%的貿易應收款項總額及合約資產分別來自貴集團五大客 |
| 3.3 | 13 | table | 0.07 | 正如我們在財務報表中所確認，我們的客戶包括國有建築企業及房地產開發商。截至2018年12月31日止三個年度各年及截至2019年9月30日止九個月，我們的五大客戶為我們的總收益分別貢獻約99.6%、90.2%、85.9%及91.0%。於往績記錄期間，我們的大部分收益均來自客戶A。截至2018年12月31日止三個年度各年及截至2019年9月30日止九個月，客戶A分別佔我們總收益的約83.2%、69.5 |
| 3.3 | 475 | table | 0.08 | 貴集團的信貸風險主要受每名客戶的個別特徵而非客戶業務所在行業的影響，因此，貴集團主要在面臨個別客戶帶來的重大風險時產生高度集中的信貸風險。於2016年、2017年及2018年12月31日以及2019年9月30日，77.9%、66.1%、53.1%及65.8%的貿易應收款項總額及合約資產來自貴集團最大客戶，99.5%、85.6%、79.2%及87.2%的貿易應收款項總額及合約資產分別來自貴集團五大客 |
| 3.5 | — | — | — | （已跳过：non-biotech） |

### 3.4 计分证据（score_breakdown）

#### `RELATED_PARTY_HIGH`（+25.0，doc§3.2）

- p42（text）：於本招股章程中，除文義另有所指外，否則「聯繫人」、「緊密聯繫人」、「關連人士」、「關連交易」、「控股股東」、「核心關連人士」、「附屬公司」及「主要股東」等詞彙均具有上市規則所賦予的涵義。
- p226（table）：福建潤江95.0%的股權由本公司執行董事兼董事長、控股股東荀名紅先生持有。由於荀名紅先生持有福建潤江超過30.0%的股權，根據上市規則第14A章，福建潤江被視為荀名紅先生的聯繫人及本公司的關連人士。進一步詳情請參閱「關連交易」。福建潤江為一間投資控股公司。
- p359（text）：(ii)該等關聯方交易不會致使本集團往績記錄期間的經營業績失真或導致本集團的過往業績不能反映本集團的未來表現；(iii)除「關連交易」所披露的關連交易外，所有其他關聯方交易將於上市後終止；及(iv)所有與關聯方的非貿易結餘將於上市前結清。
- p42（text）：於本招股章程中，除文義另有所指外，否則「聯繫人」、「緊密聯繫人」、「關連人士」、「關連交易」、「控股股東」、「核心關連人士」、「附屬公司」及「主要股東」等詞彙均具有上市規則所賦予的涵義。
- p226（table）：福建潤江95.0%的股權由本公司執行董事兼董事長、控股股東荀名紅先生持有。由於荀名紅先生持有福建潤江超過30.0%的股權，根據上市規則第14A章，福建潤江被視為荀名紅先生的聯繫人及本公司的關連人士。進一步詳情請參閱「關連交易」。福建潤江為一間投資控股公司。

#### `CONCENTRATION_HIGH`（+25.0，doc§3.3）

- p13（table）：我們的供應商主要包括混凝土、樁、鋼筋及木材模板等材料供應商。截至2018年12月31止三個年度各年及截至2019年9月30日止九個月，我們的五大供應商分別合共佔我們材料採購總額的約55.3%、38.6%、35.7%及32.0%，而我們的最大供應商於各年度／期間分別佔我們同期材料採購總額的約16.8%、11.6%、12.1%及13.1%。於往績記錄期間，我們亦按項目基準委聘分包商(主要包括勞務分包商
- p13（table）：我們的供應商主要包括混凝土、樁、鋼筋及木材模板等材料供應商。截至2018年12月31止三個年度各年及截至2019年9月30日止九個月，我們的五大供應商分別合共佔我們材料採購總額的約55.3%、38.6%、35.7%及32.0%，而我們的最大供應商於各年度／期間分別佔我們同期材料採購總額的約16.8%、11.6%、12.1%及13.1%。於往績記錄期間，我們亦按項目基準委聘分包商(主要包括勞務分包商
- p475（table）：貴集團的信貸風險主要受每名客戶的個別特徵而非客戶業務所在行業的影響，因此，貴集團主要在面臨個別客戶帶來的重大風險時產生高度集中的信貸風險。於2016年、2017年及2018年12月31日以及2019年9月30日，77.9%、66.1%、53.1%及65.8%的貿易應收款項總額及合約資產來自貴集團最大客戶，99.5%、85.6%、79.2%及87.2%的貿易應收款項總額及合約資產分別來自貴集團五大客
- p13（table）：正如我們在財務報表中所確認，我們的客戶包括國有建築企業及房地產開發商。截至2018年12月31日止三個年度各年及截至2019年9月30日止九個月，我們的五大客戶為我們的總收益分別貢獻約99.6%、90.2%、85.9%及91.0%。於往績記錄期間，我們的大部分收益均來自客戶A。截至2018年12月31日止三個年度各年及截至2019年9月30日止九個月，客戶A分別佔我們總收益的約83.2%、69.5
- p475（table）：貴集團的信貸風險主要受每名客戶的個別特徵而非客戶業務所在行業的影響，因此，貴集團主要在面臨個別客戶帶來的重大風險時產生高度集中的信貸風險。於2016年、2017年及2018年12月31日以及2019年9月30日，77.9%、66.1%、53.1%及65.8%的貿易應收款項總額及合約資產來自貴集團最大客戶，99.5%、85.6%、79.2%及87.2%的貿易應收款項總額及合約資產分別來自貴集團五大客

### 3.5 工具调用链

- 耗时：`4.135s`

1. **`retrieve_legal`**
   ```json
   {"source": "offline:/nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_jianzhong_legal.json", "fields": ["REDEMPTION_CLAUSE", "RELATED_PARTY", "CONCENTRATION", "CASH_BURN_PRESSURE", "PRE_IPO_VALUATION"], "per_query": 5, "has_evidence_by_field": true, "hint": null}
   ```
2. **`parse_grep`**
   ```json
   {"path": "/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/00589_28-02-2020_建中建設_股份發售/full_parse.json", "hits": 0, "pages": []}
   ```
3. **`retrieve_section_evidence`**
   ```json
   {"intents": {"redemption": {"hits": 0, "pages": [], "route": [{"section_id": "history_and_corporate_structure", "section_title": "歷史、重組及公司架構", "start_page": 124, "end_page": 145, "confidence": 0.95}, {"section_id": "risk_factors", "section_title": "風險因素", "start_page": 48, "end_page": 86, "confidence": 0.95}]}, "related_party": {"hits": 8, "pages": [268, 265, 248, 226, 359, 264, 246, 265], "route": [{"section_id": "connected_transactions", "section_title": "關連交易", "start_page": 264, "end_page": 268, "confidence": 0.95}, {"section_id": "business", "section_title": "業務", "start_page": 146, "end_page": 255, "confidence": 0.95}, {"section_id": "financial_information", "section_title": "財務資料", "start_page": 292, "end_page": 365, "confidence": 0.95}]}, "concentration": {"hits": 5, "pages": [199, 54, 218, 199, 195], "route": [{"section_id": "business", "section_title": "業務", "start_page": 146, "end_page": 255, "confidence": 0.95}, {"section_id": "risk_factors", "section_title": "風險因素", "start_page": 48, "end_page": 86, "confidence": 0.95}, {"section_id": "financial_information", "section_title": "財務資料", "start_page": 292, "end_page": 365, "confidence": 0.95}]}}}
   ```
4. **`extract_legal`**
   ```json
   {"sections": {"3.1": {"exists": false, "skipped": null, "evidence_n": 0, "search_log": {"keywords_tried": ["赎回", "贖回", "对赌", "對賭", "回购", "回購", "优先股", "優先股", "领售", "領售", "撤资", "撤資", "贖回權", "可換股", "可转换可赎回", "可轉換可贖回", "股东协议", "股東協議", "特别权利", "特別權利", "赎回权终止", "特別權利終止"], "pages_scanned": [500, 525, 526, 560], "raw_hits": 5, "filtered_noise": 0, "strong_hits": 0, "note": "已检索无命中强对赌/赎回/优先股模式"}, "top1_supplier_pct": null, "top5_supplier_pct": null}, "3.2": {"exists": true, "skipped": null, "evidence_n": 5, "search_log": null, "top1_supplier_pct": null, "top5_supplier_pct": null}, "3.3": {"exists": true, "skipped": null, "evidence_n": 5, "search_log": null, "top1_supplier_pct": 100.0, "top5_supplier_pct": 100.0}, "3.5": {"exists": null, "skipped": true, "evidence_n": 0, "search_log": null, "top1_supplier_pct": null, "top5_supplier_pct": null}}}
   ```
5. **`score_legal`**
   ```json
   {"risk_score": 50.0, "breakdown_n": 2}
   ```

### 3.6 分析结论

- 风险分 **50.0**（medium）。打分来自披露基础分或规则命中（见 score_breakdown）。
- 3.1 对赌/赎回：exists=`False`，证据强度=`low`
- 3.2 关联交易：exists=`True`，占比=`95.0`。
- 3.3 集中度：exists=`True`，证据页=[13, 13, 475, 13, 475]。
- 3.5 管线风险按 non-biotech 正确跳过。

## 4. 改进建议

1. **[已做] 财务 LLM 主路径**：retrieve → extract_metrics → gates → analyze_finance(单次四维 LLM) → 可解释评分；规则打分降为 fallback（`--finance-rules-only`）。
2. **[已做] Gemma4 reasoning**：OpenRouter `reasoning.enabled`；日志区分 `[model_think]` / `[structured_reasoning]`。
3. **[已做] 推理日志落盘**：`logs/{doc}_{agent}_{ts}.log` + `.jsonl`（时间/文档/流程/工具skills/过程/结果/推理链）。
4. **[已做] 财务 BS 交叉校验**：若 TOTAL_ASSETS < NET_ASSETS，用 NET+LIAB 回填。
5. **法务检索源**：可用 `--use-live-retrieval`；`--use-llm` 做法务结构化增强。

---

_本报告由 `scripts/generate_analysis_report.py` 根据 Agent 结构化输出自动生成。_
