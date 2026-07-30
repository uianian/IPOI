# 小米集团 — 财务/法务 Agent 结果分析报告

- 生成时间：2026-07-21 10:50:14
- 招股书：`xiaomi.pdf`
- doc_id：`e5a29706-4a68-4569-b9af-d3e49436f49d`
- 参考基本面融合分：`None` （legal×0.45 + finance×0.55；总控未启用）
- 说明：—

## 1. 总览

| Agent | 风险分 (0-100↑风险) | 等级 | 摘要 |
|-------|---------------------|------|------|
| 财务穿透 | **0.0** | very_low | 财务指标11项；3.4=跳过(profitable)；风险分 0.0 (very_low)；阴性发现3条 |
| 法务合规 | **None** | None |  |

## 2. 财务穿透 Agent

### 2.1 得分与分解

_无扣分项（未触发风险规则，或证据不足未计分）_

### 2.2 门控

```json
{
  "is_unprofitable": false,
  "latest_full_year_loss": false,
  "continuous_net_loss": false,
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

### 2.3 抽取指标

| 指标 | 2015 | 2016 | 2017 | 2018 | 2017_i1 | p4 | p5 |
|------|------|------|------|------|------|------|------|
| REV | 66,811,258 | 68,434,161 | 114,624,742 | 34,412,362 | 18,531,793 | — | — |
| COGS | -64,111,325 | -61,184,806 | -99,470,537 | -30,110,935 | -16,067,675 | — | — |
| GP | 2,699,933 | 7,249,355 | 15,154,205 | 4,301,427 | 2,464,118 | — | — |
| RD_EXP | -1,511,815 | -2,104,226 | -3,151,401 | -1,103,775 | -604,689 | — | — |
| SGA | -766,252 | -926,833 | -1,216,110 | -465,323 | -240,209 | — | — |
| TOTAL_ASSETS | 39,136,537 | 50,765,601 | 89,869,761 | 92,093,600 | — | 150.00 | 150.00 |
| TOTAL_LIAB | 39,136,537 | 50,765,601 | 89,869,761 | 92,093,600 | — | — | — |
| NET_ASSETS | -86,638,308 | -92,057,875 | -127,210,691 | -127,991,061 | — | 2,015 | 2,016 |
| CASH_EQ | 8,394,078 | 9,230,320 | 11,563,282 | 14,027,013 | — | 24,952,527 | 30,636,318 |
| CV_PREF | 105,932,869 | 115,802,177 | 161,451,203 | 165,330,822 | — | — | — |
| GP_MARGIN | 4.04 | 10.59 | 13.22 | 12.50 | 13.30 | — | — |

3.4 现金消耗：skipped=`True`，reason=`profitable`，runway=`None`

### 2.4 召回证据（主表）

| 表/字段 | 页码 | 类型 | 命中数 | 年份列 | 摘录 |
|--------|------|------|--------|--------|------|
| TBL_IS | 467 | table | — | — | 附註 截至12月31日止年度 截至3月31日止三個月 2015年人民幣千元 2016年人民幣千元 2017年人民幣千元 2017年人民幣千元（未經審核） 2018年人民幣千元 收入 6 66,811,258 68,434,161 114,624,742 18,531,793 34,412,362 銷售成本 9 (64,111,325) (61,184,806) (99,470,537) (16,… |
| TBL_BS | 469 | table | — | — | 附註 2015年 人民幣千元 2016年 人民幣千元 2017年 人民幣千元 2018年 人民幣千元 資產 非流動資產 土地使用權 15 — 3,494,041 3,416,359 3,396,938 物業及設備 16 290,183 848,377 1,730,872 2,099,305 無形資產 17 553,759 1,120,133 2,274,352 2,246,404 按權益法入賬之… |
| TBL_CF | 477 | table | — | — | 截至12月31日止年度 截至3月31日止三個月 附註 2015年人民幣千元 2016年人民幣千元 2017年人民幣千元 2017年人民幣千元（未經審核） 2018年人民幣千元 經營活動現金流量 經營(所用)／所得現金 (2,293,755) 4,714,517 527,321 (1,134,445) (987,888) 已付所得稅 (307,556) (183,253) (1,522,990) … |

### 2.5 工具调用链

- 耗时：`0.026s`

1. **`retrieve_finance`**
   ```json
   {"source": "offline:../../retrieval/.runtime/agent_retrieval_xiaomi.json", "tables": ["TBL_IS", "TBL_BS", "TBL_CF"], "skipped_fields": 8}
   ```
2. **`extract_financials_from_tables`**
   ```json
   {"metrics": ["REV", "COGS", "GP", "RD_EXP", "SGA", "TOTAL_ASSETS", "TOTAL_LIAB", "NET_ASSETS", "CASH_EQ", "CV_PREF", "GP_MARGIN"], "years": ["2015", "2016", "2017", "2018"], "bs_reconcile": {"changed": false, "notes": ["2015: TOTAL_ASSETS=39136537.0 与 NET+LIAB=-47501771.0 偏差>15%（保留原值）", "2016: TOTAL_ASSETS=50765601.0 与 NET+LIAB=-41292274.0 偏差>15%（保留原值）", "2017: TOTAL_ASSETS=89869761.0 与 NET+LIAB=-37340930.0 偏差>15%（保留原值）", "2018: TOTAL_ASSETS=92093600.0 与 NET+LIAB=-35897461.0 偏差>15%（保留原值）"], "TOTAL_ASSETS_RECONCILED": {}}}
   ```
3. **`detect_profitability_and_issuer`**
   ```json
   {"gates": {"is_unprofitable": false, "is_biotech_18a": false, "skip_3_4": true, "skip_2_4": true, "skip_3_5": true, "skip_3_4_reason": "profitable", "skip_2_4_reason": "non-biotech"}}
   ```
4. **`extract_cash_burn`**
   ```json
   {"result": {"skipped": true, "reason": "profitable", "CASH_RUNWAY_MONTHS": null}}
   ```
5. **`score_finance`**
   ```json
   {"risk_score": 0.0, "breakdown_n": 0, "negative_findings_n": 3}
   ```

### 2.6 分析结论

- 风险分 **0.0**（very_low）。门控：未盈利=`False`，跳过3.4=`True`（profitable），跳过2.4=`True`（non-biotech）。
- 收入与毛利率已抽出：2021–2023 收入约 —→—（千元），毛利率约 —%→—%。
- 主表证据定位：TBL_IS@p467, TBL_BS@p469, TBL_CF@p477（附录一附近，符合 finance profile 整表召回）。

### 2.7 阴性发现（低风险说明）

- **PROFITABLE**（doc§2.1）：业绩记录期盈利（期内利润为正），未触发连续亏损规则
- **SKIP_CASH_BURN**（doc§3.4）：跳过 3.4 现金跑道（原因：profitable）
- **GP_MARGIN_STABLE**（doc§2.1）：毛利率相对稳定（4.04% → 12.50%），未出现 >5pct 恶化

### 2.8 资产负债表交叉校验

- 2015: TOTAL_ASSETS=39136537.0 与 NET+LIAB=-47501771.0 偏差>15%（保留原值）
- 2016: TOTAL_ASSETS=50765601.0 与 NET+LIAB=-41292274.0 偏差>15%（保留原值）
- 2017: TOTAL_ASSETS=89869761.0 与 NET+LIAB=-37340930.0 偏差>15%（保留原值）
- 2018: TOTAL_ASSETS=92093600.0 与 NET+LIAB=-35897461.0 偏差>15%（保留原值）

## 3. 法务合规 Agent

### 3.1 得分与分解

_无扣分项（未触发风险规则，或证据不足未计分）_

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

### 3.5 工具调用链

_无工具调用记录_

### 3.6 分析结论

- 风险分 **None**（None）。打分来自披露基础分而非高危阈值命中（见 score_breakdown）。
- 3.1 对赌/赎回：exists=`None`，证据强度=`None`（未找到优先股赎回等强模式，符合消费品牌已上市前清理对赌的常见情况，但仍建议人工抽查「历史及发展/投资协议」章节）
- 3.2 关联交易：exists=`None`，占比=`None`。当前证据页偏「核心关连人士/购回股份授权」，**未必等于关连交易金额披露**，存在主题漂移风险。
- 3.3 集中度：exists=`None`，证据页=None。已召回供应商排名表表头，但 **未抽出 top1/top5 百分比数值**，故只给了 disclosure 基础分 (+12)，未触发 >50% 高危分。

## 4. 改进建议

1. **[已做] 财务 BS 交叉校验**：若 TOTAL_ASSETS < NET_ASSETS，用 NET+LIAB 回填；不纠结召回是 text 还是 HTML（上游解析限制，文本表直接喂 Agent）。
2. **[已做] 财务证据落盘**：`evidence_summary.snippets` / `table_meta.excerpt` 写入 50–200 字切片。
3. **法务检索源**：离线旧 JSON 无 evidence_by_field 时自动提示；可用 `--use-live-retrieval` 对蜜雪重跑 retrieval legal profile 获得字段级混合检索。
4. **[已做] 3.2 主题过滤**：排除股份购回授权噪声，优先「关连交易/持续关连/豁免」；`--use-llm` 可从候选段抽金额与占比。
5. **[已做] 3.3 数值抽取**：解析比例列写入 top1/top5 customer/supplier pct，可触发 >50% 高危分。
6. **[已做] 3.1 检索日志**：exists=false 时附带 search_log（关键词、扫描页、过滤统计）。
7. **[已做] 阴性发现**：财务低分时输出 PROFITABLE / CFO_POSITIVE / GP_MARGIN_STABLE 等说明。
8. **端到端评测**：`--use-live-retrieval` 做在线混合检索；`--use-llm` 做法务结构化增强；再与人工标注对比召回率/准确率（目标 ≥85% / ≥80%）。详见 README「Live retrieval / LLM」。

---

_本报告由 `scripts/generate_analysis_report.py` 根据 Agent 结构化输出自动生成。_
