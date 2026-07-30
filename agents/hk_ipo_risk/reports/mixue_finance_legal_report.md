# 蜜雪集團 — 财务/法务 Agent 结果分析报告

- 生成时间：2026-07-20 19:31:17
- 招股书：`02097_21-02-2025_蜜雪集團_全球發售.pdf`
- doc_id：`136ee620-0473-450b-a566-72172824cdec`
- 参考基本面融合分：`5.4` （legal×0.45 + finance×0.55；总控未启用）
- 说明：reference_fundamental_score = legal*0.45 + finance*0.55; master agent 未启用

## 1. 总览

| Agent | 风险分 (0-100↑风险) | 等级 | 摘要 |
|-------|---------------------|------|------|
| 财务穿透 | **0.0** | very_low | 财务指标16项；3.4=跳过(profitable)；风险分 0.0 (very_low)；阴性发现4条 |
| 法务合规 | **12.0** | very_low | 法务 3.1/3.2/3.3 抽取完成；3.5=跳过；风险分 12.0 (very_low) |

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

| 指标 | 2021 | 2022 | 2023 | 2024 | 2023_i1 |
|------|------|------|------|------|------|
| REV | 10,350,986 | 13,575,577 | 20,302,465 | 18,659,671 | 15,393,328 |
| COGS | -7,107,124 | -9,728,740 | -14,303,498 | -12,619,249 | -10,817,689 |
| GP | 3,243,862 | 3,846,837 | 5,998,967 | 6,040,422 | 4,575,639 |
| RD_EXP | -17,151 | -32,304 | -85,000 | -64,805 | -51,343 |
| SGA | -405,766 | -774,431 | -1,318,588 | -1,097,090 | -992,934 |
| NET_LOSS | 1,911,942 | 2,013,091 | 3,186,605 | 3,490,972 | 2,452,779 |
| TOTAL_ASSETS | 7,248,888 | 9,817,920 | 14,329,778 | 18,385,457 | — |
| TOTAL_LIAB | 1,706,178 | 2,338,653 | 3,734,313 | 4,289,251 | — |
| NET_ASSETS | 5,542,710 | 7,479,267 | 10,595,465 | 14,096,206 | — |
| CASH_EQ | 2,675,827 | 2,764,138 | 5,621,904 | 5,980,396 | — |
| CFO | 1,692,389 | 2,430,631 | 3,793,872 | 5,100,754 | 3,091,691 |
| CFI | -1,831,630 | -2,201,861 | -825,344 | -4,485,997 | -1,997,140 |
| CFF | 726,648 | -139,261 | -111,319 | -257,162 | -102,786 |
| END_CASH | 2,675,827 | 2,764,138 | 5,621,904 | 5,980,396 | 3,759,213 |
| GP_MARGIN | 31.34 | 28.34 | 29.55 | 32.37 | 29.72 |
| TOTAL_ASSETS_RECONCILED | 7,248,888 | 9,817,920 | 14,329,778 | 18,385,457 | — |

3.4 现金消耗：skipped=`True`，reason=`profitable`，runway=`None`

### 2.4 召回证据（主表）

| 表/字段 | 页码 | 类型 | 命中数 | 年份列 | 摘录 |
|--------|------|------|--------|--------|------|
| TBL_IS | 428 | table | — | — | 附註 截至12月31日止年度 截至9月30日止九個月 2021年 2022年 2023年 2023年 2024年 人民幣千元 人民幣千元 人民幣千元 人民幣千元 人民幣千元 收入 5 10,350,986 13,575,577 20,302,465 15,393,328 18,659,671 銷售成本 (7,107,124) (9,728,740) (14,303,498) (10,817,68… |
| TBL_BS | 430 | text | — | — | 附註 於12月31日 於9月30日 2021年 2022年 2023年 2024年 人民幣千元 人民幣千元 人民幣千元 人民幣千元 非流動資產 物業、廠房及設備 14 1,033,497 1,701,086 3,390,053 5,156,514 使用權資產 15(a) 166,031 445,560 426,986 378,520 其他無形資產 16 9,029 20,591 25,624 2… |
| TBL_CF | 437 | table | — | — | 截至12月31日止年度 截至9月30日止九個月 2021年 2022年 2023年 2023年 2024年 人民幣千元 人民幣千元 人民幣千元 人民幣千元 人民幣千元 來自經營活動的現金流量 税前利潤： 2,558,874 2,658,043 4,154,002 3,184,655 4,568,545 就下列各項作出調整： 財務成本 8 5,973 9,190 14,697 11,037 5,4… |

### 2.5 工具调用链

- 耗时：`0.022s`

1. **`retrieve_finance`**
   ```json
   {"source": "offline:/nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_mixue.json", "tables": ["TBL_IS", "TBL_BS", "TBL_CF"], "skipped_fields": 8}
   ```
2. **`extract_financials_from_tables`**
   ```json
   {"metrics": ["REV", "COGS", "GP", "RD_EXP", "SGA", "NET_LOSS", "TOTAL_ASSETS", "TOTAL_LIAB", "NET_ASSETS", "CASH_EQ", "CFO", "CFI", "CFF", "END_CASH", "GP_MARGIN", "TOTAL_ASSETS_RECONCILED"], "years": ["2021", "2022", "2023", "2024"], "bs_reconcile": {"changed": true, "notes": ["2021: TOTAL_ASSETS 5073766.0 < NET_ASSETS 5542710.0 → 回填 NET+LIAB=7248888.0", "2022: TOTAL_ASSETS 6556065.0 < NET_ASSETS 7479267.0 → 回填 NET+LIAB=9817920.0", "2023: TOTAL_ASSETS 9148185.0 < NET_ASSETS 10595465.0 → 回填 NET+LIAB=14329778.0", "2024: TOTAL_ASSETS 11506900.0 < NET_ASSETS 14096206.0 → 回填 NET+LIAB=18385457.0"], "TOTAL_ASSETS_RECONCILED": {"2021": 7248888.0, "2022": 9817920.0, "2023": 14329778.0, "2024": 18385457.0}}}
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
   {"risk_score": 0.0, "breakdown_n": 0, "negative_findings_n": 4}
   ```

### 2.6 分析结论

- 风险分 **0.0**（very_low）。门控：未盈利=`False`，跳过3.4=`True`（profitable），跳过2.4=`True`（non-biotech）。
- 期内利润（NET_LOSS 字段存利润序列，正数=盈利）逐年为正：2021=1,911,942、2022=2,013,091、2023=3,186,605、2024=3,490,972，与「已盈利→跳过现金跑道」门控一致。
- 收入与毛利率已抽出：2021–2023 收入约 10,350,986→20,302,465（千元），毛利率约 31.34%→29.55%。
- 经营活动现金流（CFO）业绩记录期均为正，未触发 CFO 持续为负的加分规则，故财务分为 0 合理。
- 主表证据定位：TBL_IS@p428, TBL_BS@p430, TBL_CF@p437（附录一附近，符合 finance profile 整表召回）。

### 2.7 阴性发现（低风险说明）

- **PROFITABLE**（doc§2.1）：业绩记录期盈利（期内利润为正），未触发连续亏损规则
- **SKIP_CASH_BURN**（doc§3.4）：跳过 3.4 现金跑道（原因：profitable）
- **CFO_POSITIVE**（doc§2.3）：经营活动现金流（CFO）业绩记录期均为正
- **GP_MARGIN_STABLE**（doc§2.1）：毛利率相对稳定（31.34% → 32.37%），未出现 >5pct 恶化

### 2.8 资产负债表交叉校验

- 2021: TOTAL_ASSETS 5073766.0 < NET_ASSETS 5542710.0 → 回填 NET+LIAB=7248888.0
- 2022: TOTAL_ASSETS 6556065.0 < NET_ASSETS 7479267.0 → 回填 NET+LIAB=9817920.0
- 2023: TOTAL_ASSETS 9148185.0 < NET_ASSETS 10595465.0 → 回填 NET+LIAB=14329778.0
- 2024: TOTAL_ASSETS 11506900.0 < NET_ASSETS 14096206.0 → 回填 NET+LIAB=18385457.0

## 3. 法务合规 Agent

### 3.1 得分与分解

| 代码 | 加分 | 规则 | 说明 | 证据页 |
|------|------|------|------|--------|
| CONCENTRATION_DISCLOSURE | +12.0 | doc§3.3 | 存在客户/供应商集中度披露 | 273, 274, 275 |

### 3.2 章节特征摘要

| 章节 | exists/skipped | 强度 | 关键字段 |
|------|----------------|------|----------|
| 3.1 | exists=False | low | — |
| 3.2 | exists=False | low | — |
| 3.3 | exists=True | high | — |
| 3.4 | exists=None | — | owner=finance |
| 3.5 | skipped=True | — | reason=non-biotech |
| 3.6 | exists=None | — | — |

### 3.3 召回证据明细

| 章节 | 页码 | 类型 | 置信度 | 摘录 |
|------|------|------|--------|------|
| 3.1 | — | — | — | 未召回强证据 / 判定不存在 |
| 3.2 | — | — | — | 未召回强证据 / 判定不存在 |
| 3.3 | 273 | table | 2.00 | 1 . . . 供應商A 食材 一家提供食品飲料產品的公司 2015年 426,084 5.0 2 . . . 供應商B 食材 一家提供食品飲料產品的公司 2019年 |
| 3.3 | 274 | table | 2.00 | 1 . . . . 供應商A 食材 一家提供食品飲料產品的公司 2015年 510,452 4.6 2 . . . . 供應商E 食材 一家提供食品飲料產品的公司 2017年< |
| 3.3 | 275 | table | 2.00 | 1．．．． 供應商H 商業樓宇 一家從事房地產開發及營運的公司 2020年 936,543 6.5 2．．．． 供應商A 食材 一家提供食品飲料產品的公司 2015年 |
| 3.3 | 273 | table | 2.00 | 排名 供應商 所採購物品 背景 業務合作起始年份 採購額 佔總採購額比例 人民幣千元 % |
| 3.3 | 274 | table | 2.00 | 排名 供應商 所採購物品 背景 業務合作起始年份 採購額 佔總採購額比例 人民幣千元 % |
| 3.5 | — | — | — | （已跳过：non-biotech） |

### 3.4 计分证据（score_breakdown）

#### `CONCENTRATION_DISCLOSURE`（+12.0，doc§3.3）

存在客户/供应商集中度披露

- p273（table）：1 . . . 供應商A 食材 一家提供食品飲料產品的公司 2015年 426,084 5.0 2 . . . 供應商B 食材 一家提供食品飲料產品的公司 2019年
- p274（table）：1 . . . . 供應商A 食材 一家提供食品飲料產品的公司 2015年 510,452 4.6 2 . . . . 供應商E 食材 一家提供食品飲料產品的公司 2017年<
- p275（table）：1．．．． 供應商H 商業樓宇 一家從事房地產開發及營運的公司 2020年 936,543 6.5 2．．．． 供應商A 食材 一家提供食品飲料產品的公司 2015年
- p273（table）：排名 供應商 所採購物品 背景 業務合作起始年份 採購額 佔總採購額比例 人民幣千元 %
- p274（table）：排名 供應商 所採購物品 背景 業務合作起始年份 採購額 佔總採購額比例 人民幣千元 %

### 3.5 工具调用链

- 耗时：`0.013s`

1. **`retrieve_legal`**
   ```json
   {"source": "offline:/nfs/users/wuqianqian/IPOI/agents/ipo/.runtime/agent_retrieval_mixue_legal.json", "fields": [], "per_query": 2, "has_evidence_by_field": false, "hint": "旧格式/字段索引为空：依赖 parse_grep；建议 --use-live-retrieval 重跑 legal profile"}
   ```
2. **`parse_grep`**
   ```json
   {"path": "/nfs/users/wuqianqian/IPOI/pdf_parsing/output/mixue/risk_chunks.json", "hits": 13, "pages": [273, 273, 274, 274, 275, 275, 39, 48, 51, 70]}
   ```
3. **`extract_legal`**
   ```json
   {"sections": {"3.1": {"exists": false, "skipped": null, "evidence_n": 0, "search_log": {"keywords_tried": ["赎回", "贖回", "对赌", "對賭", "回购", "回購", "优先股", "優先股", "领售", "領售", "撤资", "撤資", "贖回權", "可換股", "可转换可赎回", "可轉換可贖回", "股东协议", "股東協議", "特别权利", "特別權利", "赎回权终止", "特別權利終止"], "pages_scanned": [352, 501], "raw_hits": 2, "filtered_noise": 1, "strong_hits": 0, "note": "已检索无命中强对赌/赎回/优先股模式"}, "top1_supplier_pct": null, "top5_supplier_pct": null}, "3.2": {"exists": false, "skipped": null, "evidence_n": 0, "search_log": null, "top1_supplier_pct": null, "top5_supplier_pct": null}, "3.3": {"exists": true, "skipped": null, "evidence_n": 5, "search_log": null, "top1_supplier_pct": 6.5, "top5_supplier_pct": 47.1}, "3.5": {"exists": null, "skipped": true, "evidence_n": 0, "search_log": null, "top1_supplier_pct": null, "top5_supplier_pct": null}}}
   ```
4. **`score_legal`**
   ```json
   {"risk_score": 12.0, "breakdown_n": 1}
   ```

### 3.6 分析结论

- 风险分 **12.0**（very_low）。打分来自披露基础分而非高危阈值命中（见 score_breakdown）。
- 3.1 对赌/赎回：exists=`False`，证据强度=`low`（未找到优先股赎回等强模式，符合消费品牌已上市前清理对赌的常见情况，但仍建议人工抽查「历史及发展/投资协议」章节）
- 3.2 关联交易：exists=`False`，占比=`None`。当前证据页偏「核心关连人士/购回股份授权」，**未必等于关连交易金额披露**，存在主题漂移风险。
- 3.3 集中度：exists=`True`，证据页=[273, 274, 275, 273, 274]。已召回供应商排名表表头，但 **未抽出 top1/top5 百分比数值**，故只给了 disclosure 基础分 (+12)，未触发 >50% 高危分。
- 3.5 管线风险按 non-biotech 正确跳过。

### 3.7 3.1 检索日志（无命中时仍可审计）

```json
{
  "keywords_tried": [
    "赎回",
    "贖回",
    "对赌",
    "對賭",
    "回购",
    "回購",
    "优先股",
    "優先股",
    "领售",
    "領售",
    "撤资",
    "撤資",
    "贖回權",
    "可換股",
    "可转换可赎回",
    "可轉換可贖回",
    "股东协议",
    "股東協議",
    "特别权利",
    "特別權利",
    "赎回权终止",
    "特別權利終止"
  ],
  "pages_scanned": [
    352,
    501
  ],
  "raw_hits": 2,
  "filtered_noise": 1,
  "strong_hits": 0,
  "note": "已检索无命中强对赌/赎回/优先股模式"
}
```

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
