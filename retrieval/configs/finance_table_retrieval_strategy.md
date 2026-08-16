# 财务主表通用检索策略（一份配置，全公司复用）

**唯一实现配置**：`configs/agent_retrieval_profiles.yaml` → `finance`  
**不要**为蜜雪/小米/快手各写一份 profile；差异用「别名表 + 门控 + 跨页 pack」吸收。

验证样本（同一策略）：

| 公司 | 用语习惯 | IS | BS | CF |
|------|----------|----|----|----|
| 蜜雪冰城 | 綜合… | p428–429 | p430–431（text） | p437–440 |
| 小米集团 | 合併… | p467–468 | p469–470（text+table） | p477 |
| 快手 | 合併… | p580–581 | p582–583（非貴公司） | p591–592 |

---

## 1. 目标

为下游抽取提供 **附录一三张主表整表包**（不是每指标 Top-K）：

| 代码 | 业务名 | 覆盖字段 |
|------|--------|----------|
| `TBL_IS` | 综合/合并损益表（+全面收益续表） | REV, COGS, GP, … |
| `TBL_BS` | 综合财务状况表 / 合并资产负债表 | TOTAL_ASSETS, … |
| `TBL_BS_COMPANY` | 贵公司（母公司）财务状况表 | 无（证据专用，不写入 `field_table_map`） |
| `TBL_CF` | 综合/合并现金流量表 | CFO, CFI, CFF, END_CASH |

输出：`evidence_by_table` + `field_table_map`；抽数交给特征抽取，不在检索层切行。  
集团指标只从 `TBL_BS` 抽；`TBL_BS_COMPANY` 单独召回，**不**并入合并 BS 的跨页 pack（遇「貴公司財務狀況表」仍作 stop title）。

---

## 2. 统一流水线（所有发行人相同）

```
Grep ∪ BM25 ∪ Vector ∪ row_label
  → same-page expand（title→table/text）
  → appendix_only 过滤（只要附录一）
  → require_title_hint（表名白名单）
  → row_labels + must_have_groups（核心行名）
  → statement_kind 互斥（IS / BS / CF / 贵公司表 / 税项附注）
  → cross_page_continue（同表「續/(續)」合并；遇下一主表/附注停止）
  → 重叠 pack 折叠（最早种子 + 最长跨度）
  → Top-K（通常附录主表只剩 1 条）
```

权重默认：`grep 0.40 / bm25 0.25 / vector 0.35`。

---

## 3. 硬性规则（查漏补缺后的共识）

### 3.1 只取附录一

- `appendix_only: true`
- **不要**概要、MD&A 讨论节作为终值来源（可另开校验通道，但不进主表 Top-K）

### 3.2 表名双语/双习惯（綜合 ↔ 合併）

| 表 | title_hints / grep 必须同时覆盖 |
|----|--------------------------------|
| IS | 綜合損益表、合併損益表、损益及其他全面/綜合收益表（含「合併損益及其他綜合收益表」） |
| BS | 綜合財務狀況表、合併財務狀況表、**合併資產負債表** |
| CF | 綜合現金流量表、合併現金流量表 |

`require_title_hint: true`：标题须**以表名 hint 起头**（允许 `—續` / `(續)`），
避免「於合併損益表確認的項目」等附注标题误命中。

### 3.3 核心行名门控（表内指标，不是表名）

- **IS**：收入类（含 18A「其他收入」「其他收入及收益」）∧（成本/毛利/期间损益/税前虧損/年內／期內虧損/研究及開發成本）；`allow_text_as_table`
- **BS**：总资产类（含「非流动/流动资产总值」「资产总值减流动负债」）∧（净值/权益/负债）；`allow_text_as_table`；
  跨页半表（上半资产、下半负债）必须 pack 合并后再做 must_have
- **CF**：经营活动类 ∧（投资或融资类）；`allow_text_as_table`；行名别名必须覆盖：
  - 蜜雪：`經營活動所得現金流量淨額`
  - 小米：`經營活動現金流量` / `經營(所用)／所得現金`
  - 快手：`經營活動所得現金流量` / `經營所得／(所用)現金` / `經營活動所得／(所用)現金淨額`

### 3.4 表类型互斥

| 规则 | 原因 |
|------|------|
| `TBL_BS` 拒收 `company_balance_sheet` | 合并表与母公司表分离 |
| `TBL_BS_COMPANY` 只收贵公司标题 | 方案 A：独立 `table_type=company_balance_sheet` |
| 合併綜合收益表 当作 BS | OCI，挂在 IS 族 |
| 税项/分部附注表 | 有收入行但无主表标题 |
| CF 误入 BS | 经营/投资现金流结构 |

### 3.5 跨页

- IS：`max_continue_pages: 2`（损益 + 全面收益）
- BS：`2`（资产页 + 负债续页；支持 `—續` / `(續)`）
- CF：`4`（蜜雪可跨 4 页；小米/快手 1–2 页也兼容）
- 重叠 pack 合并为一条；报告按 `pack_pages` **分段标页**（避免「标 469 却只显示 470 HTML」）

### 3.6 解析缺陷由检索兜底，不按公司特判

| 缺陷 | 策略 |
|------|------|
| 主表被标成 `text` | `allow_text_as_table` + 行名门控 |
| 跨页续表 | `cross_page_continue` |
| 表名用「合併」而非「綜合」 | 别名表，不写公司 if/else |

---

## 4. 明确不做的事

- 不为单家公司单独加 `profiles_mixue.yaml`
- 不在检索层按字段切 Top-K 取数（2.1–2.3）
- 不把概要表与附录主表并列进终值 Top-K
- 不依赖 `table_caption` 命名（不可靠）

---

## 5. 评测与回归命令

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/retrieval

# 同一套配置跑任意已建索引的 doc_id
python scripts/simulate_agent_retrieval.py \
  --doc-id <DOC_ID> --agent finance --issuer-type general --top-k 3 \
  --out .runtime/agent_retrieval_<name>.json

python scripts/analyze_retrieval_report.py \
  --result .runtime/agent_retrieval_<name>.json \
  --doc-name <名称> \
  --out .runtime/reports/retrieval_quality_<name>.md
```

验收标准（附录主表）：

1. IS / BS / CF 各至少 1 条，且 `table_role=appendix`
2. BS 种子页标题为合并财务状况/合并资产负债，**不是**贵公司表
3. CF 命中经营+投资/融资行名；跨页时 `pack_pages` 连续
4. 报告摘录按 pack 分段标真实页码

---

## 6. 与代码映射

| 策略点 | 代码 / 配置 |
|--------|-------------|
| 查询与别名 | `configs/agent_retrieval_profiles.yaml` |
| 附录角色 | `evidence_expand.build_page_role_map` |
| 跨页 pack / 续表 | `collect_cross_page_pack` |
| 表类型推断 | `infer_statement_kind` |
| 编排 | `agent_simulator.AgentRetrievalSimulator` |
| 报告分页展示 | `analyze_retrieval_report._render_pack_parts` |
