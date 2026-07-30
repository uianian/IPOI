# 蜜雪集團 — 财务/法务 Agent 结果分析报告

- 生成时间：2026-07-21 11:55:47
- 招股书：`02097_21-02-2025_蜜雪集團_全球發售.pdf`
- doc_id：`136ee620-0473-450b-a566-72172824cdec`
- 参考基本面融合分：`None` （legal×0.45 + finance×0.55；总控未启用）
- 财务评分模式：`llm`
- 推理日志：`/nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/logs/蜜雪集團_finance_20260721_115341.log`
- 说明：—

## 1. 总览

| Agent | 风险分 (0-100↑风险) | 等级 | 摘要 |
|-------|---------------------|------|------|
| 财务穿透 | **0.0** | very_low | 发行人盈利能力强，现金流充沛，杠杆率低，财务风险极低。 |

## 2. 财务穿透 Agent

### 2.1 得分与分解

_无扣分项（未触发风险规则，或证据不足未计分）_

### 2.2 四维分析（LLM）

#### `profitability_growth` — status=`analyzed` score=`0`

- **PROFIT_GROWTH** (low): 收入与净利润持续增长，盈利能力强且稳定 | metric=`NET_LOSS(2024): 3,490,972` | p`p428`
- **GP_STABLE** (low): 毛利率维持在30%左右，且在2024年有所提升 | metric=`GP_MARGIN(2024): 32.37%` | p`p428`

#### `cash_flow` — status=`analyzed` score=`0`

- **CFO_POSITIVE** (low): 经营活动现金流持续为正且规模扩大，利润质量高 | metric=`CFO(2024): 5,100,754` | p`p437`

#### `solvency` — status=`analyzed` score=`0`

- **LOW_LEVERAGE** (low): 资产负债率低且稳定，偿债压力极小 | metric=`DEBT_TO_ASSET_PCT(2024): 23.33%` | p`p430`

#### `business_context` — status=`skipped` score=`0`

_无 findings_


### 2.3 推理链

**[structured_reasoning]**

发行人财务状况极其稳健。收入、毛利及净利润均呈现持续增长趋势，且2024年毛利率提升至32.37%。经营活动现金流（CFO）不仅持续为正，且在2024年达到510万，显示出极强的获现能力。资产负债率维持在23%-26%的低水平，且净资产规模快速扩张。综合各项指标，未发现任何财务风险点。

**[model_think 摘录]**（全文见 logs）

> *   Issuer Type: General     *   Gates: `is_unprofitable: false`, `skip_3_4: true` (Profitable), `skip_2_4: true`.     *   Cash Burn: Skipped (because profitable).     *   Financials:         *   Revenue (REV): Growing (10.3M -> 13.5M -> 20.3M -> 18.6M (9m)).         *   Gross Profit (GP): Growing (3.2M -> 3.8M -> 5.9M -> 6.0M (9m)).         *   GP Margin: Stable/Improving (31.34% -> 28.34% -> 29.55% -> 32.37%).         *   Net Profit (NET_LOSS - Note: the key is NET_LOSS but the values are posi

### 2.4 门控

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

### 2.5 抽取指标

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
| DEBT_TO_ASSET_PCT | 23.54 | 23.82 | 26.06 | 23.33 | — |

3.4 现金消耗：skipped=`True`，reason=`profitable`，runway=`None`

### 2.6 召回证据（主表）

| 表/字段 | 页码 | 类型 | 命中数 | 年份列 | 摘录 |
|--------|------|------|--------|--------|------|
| TBL_IS | 428 | table | — | — | 附註 截至12月31日止年度 截至9月30日止九個月 2021年 2022年 2023年 2023年 2024年 人民幣千元 人民幣千元 人民幣千元 人民幣千元 人民幣千元 收入 5 10,350,986 13,575,577 20,302,465 15,393,328 18,659,671 銷售成本 (7,107,124) (9,728,740) (14,303,498) (10,817,68… |
| TBL_BS | 430 | text | — | — | 附註 於12月31日 於9月30日 2021年 2022年 2023年 2024年 人民幣千元 人民幣千元 人民幣千元 人民幣千元 非流動資產 物業、廠房及設備 14 1,033,497 1,701,086 3,390,053 5,156,514 使用權資產 15(a) 166,031 445,560 426,986 378,520 其他無形資產 16 9,029 20,591 25,624 2… |
| TBL_CF | 437 | table | — | — | 截至12月31日止年度 截至9月30日止九個月 2021年 2022年 2023年 2023年 2024年 人民幣千元 人民幣千元 人民幣千元 人民幣千元 人民幣千元 來自經營活動的現金流量 税前利潤： 2,558,874 2,658,043 4,154,002 3,184,655 4,568,545 就下列各項作出調整： 財務成本 8 5,973 9,190 14,697 11,037 5,4… |

### 2.7 工具调用链

- 耗时：`102.642s`

1. **`retrieve_finance`**
   ```json
   {"source": "offline:/nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_mixue.json", "tables": ["TBL_IS", "TBL_BS", "TBL_CF"], "skipped_fields": 8}
   ```
2. **`extract_metrics`**
   ```json
   {"metrics": ["REV", "COGS", "GP", "RD_EXP", "SGA", "NET_LOSS", "TOTAL_ASSETS", "TOTAL_LIAB", "NET_ASSETS", "CASH_EQ", "CFO", "CFI", "CFF", "END_CASH", "GP_MARGIN", "TOTAL_ASSETS_RECONCILED"], "years": ["2021", "2022", "2023", "2024"], "bs_reconcile": {"changed": true, "notes": ["2021: TOTAL_ASSETS 5073766.0 < NET_ASSETS 5542710.0 → 回填 NET+LIAB=7248888.0", "2022: TOTAL_ASSETS 6556065.0 < NET_ASSETS 7479267.0 → 回填 NET+LIAB=9817920.0", "2023: TOTAL_ASSETS 9148185.0 < NET_ASSETS 10595465.0 → 回填 NET+LIAB=14329778.0", "2024: TOTAL_ASSETS 11506900.0 < NET_ASSETS 14096206.0 → 回填 NET+LIAB=18385457.0"], "TOTAL_ASSETS_RECONCILED": {"2021": 7248888.0, "2022": 9817920.0, "2023": 14329778.0, "2024": 18385457.0}}}
   ```
3. **`gates_and_cash_burn`**
   ```json
   {"gates": {"is_unprofitable": false, "is_biotech_18a": false, "skip_3_4": true, "skip_2_4": true, "skip_3_5": true, "skip_3_4_reason": "profitable", "skip_2_4_reason": "non-biotech"}, "cash_burn": {"skipped": true, "reason": "profitable", "CASH_RUNWAY_MONTHS": null}}
   ```
4. **`analyze_finance_llm`**
   ```json
   {"risk_score": 0.0, "think_status": "ok", "duration_ms": 102590}
   ```

### 2.8 分析结论

- 评分模式 **llm**；风险分 **0.0**（very_low）。门控：未盈利=`False`，跳过3.4=`True`（profitable），跳过2.4=`True`（non-biotech）。
- 模型 think 状态：`ok`（全文见推理日志 `[model_think]`）。
- 结构化推理摘要：发行人财务状况极其稳健。收入、毛利及净利润均呈现持续增长趋势，且2024年毛利率提升至32.37%。经营活动现金流（CFO）不仅持续为正，且在2024年达到510万，显示出极强的获现能力。资产负债率维持在23%-26%的低水平，且净资产规模快速扩张。综合各项指标，未发现任何财务风险点。
- LLM 摘要：发行人盈利能力强，现金流充沛，杠杆率低，财务风险极低。
- 期内利润（NET_LOSS 字段存利润序列，正数=盈利）：2021=1,911,942、2022=2,013,091、2023=3,186,605、2024=3,490,972。
- 收入与毛利率：2021–2024 收入 10,350,986→18,659,671（千元），毛利率 31.34%→32.37%。
- 主表证据定位：TBL_IS@p428, TBL_BS@p430, TBL_CF@p437。
- 推理日志：`/nfs/users/wuqianqian/IPOI/agents/hk_ipo_risk/logs/蜜雪集團_finance_20260721_115341.log`

### 2.9 阴性发现（低风险说明）

- **PROFITABLE**（doc§3.4）：发行人已实现盈利且连续增长，无需评估现金跑道
- **CFO_QUALITY**（doc§2.1）：CFO与净利润同步增长，无明显的利润与现金流背离
- **SOLVENCY_HEALTHY**（doc§2.3）：流动资产远高于流动负债，财务结构稳健

### 2.10 资产负债表交叉校验

- 2021: TOTAL_ASSETS 5073766.0 < NET_ASSETS 5542710.0 → 回填 NET+LIAB=7248888.0
- 2022: TOTAL_ASSETS 6556065.0 < NET_ASSETS 7479267.0 → 回填 NET+LIAB=9817920.0
- 2023: TOTAL_ASSETS 9148185.0 < NET_ASSETS 10595465.0 → 回填 NET+LIAB=14329778.0
- 2024: TOTAL_ASSETS 11506900.0 < NET_ASSETS 14096206.0 → 回填 NET+LIAB=18385457.0

## 4. 改进建议

1. **[已做] 财务 LLM 主路径**：retrieve → extract_metrics → gates → analyze_finance(单次四维 LLM) → 可解释评分；规则打分降为 fallback（`--finance-rules-only`）。
2. **[已做] Gemma4 reasoning**：OpenRouter `reasoning.enabled`；日志区分 `[model_think]` / `[structured_reasoning]`。
3. **[已做] 推理日志落盘**：`logs/{doc}_{agent}_{ts}.log` + `.jsonl`（时间/文档/流程/工具skills/过程/结果/推理链）。
4. **[已做] 财务 BS 交叉校验**：若 TOTAL_ASSETS < NET_ASSETS，用 NET+LIAB 回填。
5. **法务检索源**：可用 `--use-live-retrieval`；`--use-llm` 做法务结构化增强。

---

_本报告由 `scripts/generate_analysis_report.py` 根据 Agent 结构化输出自动生成。_
