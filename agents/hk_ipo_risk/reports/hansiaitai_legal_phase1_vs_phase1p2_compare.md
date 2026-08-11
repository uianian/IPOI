# 翰思艾泰法务 Agent：仅一阶段 vs 一+二阶段 对比报告

- 生成时间：2026-08-04 23:05:14
- 模型：两者均为 `deepseek-v4-flash`（provider=deepseek）
- 样本：翰思艾泰 18A（`hansiaitai`）

| 跑次 | 节流配置 | 结果 JSON | 日志 | Dossier |
|------|----------|-----------|------|---------|
| **A：仅一阶段** | 关 translate；`max_turns=14`；search **无硬配额** | `.runtime/hansiaitai_legal_phase1_only.json` | `logs/翰思艾泰_legal_20260804_225849.*` | `.runtime/debate/hansiaitai_legal_dossier_20260804_230144.json` |
| **B：一+二阶段** | 关 translate；`max_turns=8`；search **0/1** + submit nudge | `.runtime/hansiaitai_legal_deepseek_flash.json` | `logs/翰思艾泰_legal_20260804_223225.*` | `.runtime/debate/hansiaitai_legal_dossier_20260804_223352.json` |
| 参考 | 更完整质量单篇 | — | — | `reports/hansiaitai_legal_deepseek_flash_report.md` |

---

## 1. 一句话结论

**二阶段对 Token/轮次的节流非常有效，但对「最终分数」几乎无改善（两边都是 100/very_high）；质量上两边 Skill 都能抽到核心风险，B 更干净地收束，A 因放开 search 后陷入长空转并以 auto-submit 收场。**

| 维度 | A 仅一阶段 | B 一+二阶段 | 谁更好 |
|------|------------|-------------|--------|
| 规则整段回退 | 否（`react+rules_floor`） | 否 | 平 |
| 风险分/等级 | 100 / very_high | 100 / very_high | 平（均过激） |
| ReAct 可见 Token | **163,787** | **31,982** | **B 省约 80%** |
| 轮次 | 14（打满） | 6 | **B** |
| 收束方式 | **auto-submit**（未主动 submit） | 自主 `submit_legal_report` | **B** |
| search 次数 | **7** | **0** | B 更省；A 补证更「勤」但收益存疑 |
| 空转轮（无工具） | **8**（t7–t14） | **2**（t4–t5） | **B** |
| 空转浪费 Token | **~125,988**（占 A 总量 77%） | **~14,844**（占 B 总量 46%） | **B** |
| 耗时 | ~175s | ~87s | **B** |
| 风险点条数 | 22 codes | 21 codes | 接近 |
| 核心主题覆盖 | 赎回/特别权利/控股/IP/监管均有 | 同左 | 平 |

---

## 2. Token 对比（ReAct jsonl 可见用量）

> Skill×5 的隐藏 `chat_json` 两边都有、均未完整入账；下表只比 **ReAct 主循环**。两边都已关 translate。

| 指标 | A 仅一阶段 | B 一+二阶段 | Δ（A−B） |
|------|----------:|----------:|--------:|
| prompt | 145,375 | 24,821 | +120,554 |
| completion | 18,412 | 7,161 | +11,251 |
| **total** | **163,787** | **31,982** | **+131,805** |
| reasoning_tokens（明细） | 16,978 | 6,062 | +10,916 |
| 有工具轮合计 | ~37,799 | ~17,138 | — |
| 无工具空转合计 | ~125,988 | ~14,844 | — |

### A 分轮（节选）

| 轮 | 工具 | total |
|----|------|------:|
| 1 | retrieve | 1,656 |
| 2–3 | skill（拆成两批并行） | 2,366 + 3,916 |
| 4–5 | **search×5 + search×2** | 5,718 + **10,909** |
| 6 | rule_checks | 13,234 |
| 7–14 | **连续空转**（completion 打满 2048） | 各 ~15.5k–16k |

放开 search 后，t4–t5 把 observation 灌进历史，prompt 从 ~5k 涨到 ~13k；随后 8 轮空转每轮都在这份大上下文上再烧一遍。

### B 分轮（回顾）

`retrieve → skill×5（一轮并行）→ rule_checks → 空转×2 → submit`，无 search；末轮 prompt 仅 ~5.5k。

---

## 3. 工具链与过程质量

### A（仅一阶段）

```
retrieve
→ skill×3 + skill×2
→ search×5 + search×2   ← 二阶段本想砍掉的膨胀
→ rule_checks
→ (no_tool)×8           ← 打满 max_turns=14
→ auto-submit
```

- **优点**：按 prompt「证据不足可 search」做了补检；`legal_related_party` 标了 `confidence=low` 后触发大量 search，与设计一致。
- **严重问题**：rule_checks 之后**从未成功调 submit**，连续 8 轮只 think；依赖 `auto_submit:max_turns_exceeded_without_submit` 才出结果。过程可追踪性在后半段崩坏（大量无效 reasoning）。
- search×7 是否提升终局：最终仍 100 分；关联交易在 breakdown 里出现 `RELATED_PARTY_HIGH(+18)`（B 侧对应主题多为规则 `RELATED_PARTY_DISCLOSURE(+15)`），补证可能抬高了关联交易权重，但整体仍封顶。

### B（一+二阶段）

```
retrieve → skill×5 → rule_checks → (no_tool)×2 → submit
```

- search=0（无 coverage_hints / 配额限制生效）。
- 仍有 2 轮空转，但最终**自主 submit**，比 A 健康。
- 详见 `reports/hansiaitai_legal_deepseek_flash_report.md`。

---

## 4. 分析结果质量对比

### 4.1 分数与校准

两边都是 **100 / very_high**，相对 rules-only / Gemma 基线 **~51 / medium** 均严重偏高。  
→ **二阶段不解决评分过激**；只解决编排浪费。

### 4.2 风险码交集

- **共有 14 个 code**（核心重合）：含 `REDEMPTION_HIGH`、`RIGHTS_CLEANUP_INCOMPLETE`、`GOVERNANCE_*`、`IP_*`、`REDEMPTION_MEDIUM`、规则披露类等。
- **仅 A**：`RELATED_PARTY_HIGH`、`RELATED_PARTY_TREND`、`RELATED_PARTY_UNFAIR`、`REDEMPTION_AMOUNT_HIGH`、`INVESTIGATION_RISK`、`HUMAN_GENETIC_RESOURCE_COMPLIANCE`、`US_FDA_COMPLIANCE`、`REGULATORY_CHANGE` 等（命名更碎、偏多）。
- **仅 B**：`REGULATORY_INVESTIGATION`、`RELATED_PARTY_TERM/EXEMPTION/APPROVAL`、`LITIGATION_ABSENT`、`HUMAN_GENETIC_RESOURCE` 等。

解读：Skill 主结论稳定；差异多在**同主题换码名 / 细分条数**，以及 B 误把「无诉讼」加分（A 的 auto-submit 路径未必带上同一条）。

### 4.3 得分分解差异（进入 breakdown 的加分项）

| 主题 | A | B |
|------|---|---|
| 特别权利未清 | +20 RIGHTS_CLEANUP | +20 同 |
| 赎回 | +18 REDEMPTION_HIGH | +18 同 |
| 关联交易 | **+18 RELATED_PARTY_HIGH** | +15 RELATED_PARTY_DISCLOSURE（规则） |
| 监管 | +15 PENALTY；+8 INVESTIGATION | +18 REGULATORY_INVESTIGATION；+3 LITIGATION_ABSENT |
| 控股>50% | +10 | +10 |
| IP 驳回 | +8 | +8 |
| 集中度/管线披露 | +12/+12 | +12/+12 |

A 因 search + related_party low-conf 路径，关联交易以 **LLM high** 进分；B 更多吃规则披露分。对预警等级无差别（都封顶），对归因叙述有差别。

### 4.4 Skill 层

| Skill | A | B |
|-------|---|---|
| governance / shareholder / contracts / regulatory | high，有点 | 同 |
| related_party | **confidence=low**（促发 search） | **confidence=high** |

A 的 low-conf → 狂搜，是 Token 爆炸的直接诱因；二阶段配额从机制上截断了这条路径。

---

## 5. 综合建议

1. **保留二阶段（search 配额 + 较短 max_turns + submit nudge）**：相对仅一阶段，ReAct Token **约 16.4万 → 3.2万**，且避免 8 轮空转打满；过程质量明显更好。
2. **一阶段（关 translate）建议继续保留**：两边都无翻译开销；对比的是「有无二阶段」，不是「要不要关翻译」。
3. **评分校准是下一优先级**：两边都 100，与规则基线 51 脱节；需主题去重、抑制 ABSENT/通用风险因素加分、下调 LLM high 权重。
4. **空转仍在**：即使 B 也有 2 轮 no_tool；可对「hint 已要求 submit」强制 `tool_choice` 或缩短 reasoning，进一步省 ~1.5万。
5. **若要做公平 Token 实验**：应用同一 `max_turns` 且禁止 auto-submit 统计，或单独报「有效轮（有工具）Token」——A 有效轮其实也已到 ~3.8万，仍高于 B 的 ~1.7万（search 膨胀）。

---

## 6. 复现

```bash
# A 仅一阶段（当前代码默认）
python scripts/run_finance_legal.py --agent legal ... \
  --provider deepseek --chat-model deepseek-v4-flash \
  --out .runtime/hansiaitai_legal_phase1_only.json

# B 一+二阶段需临时恢复 max_turns=8 + search 配额后再跑
# 已有产物：.runtime/hansiaitai_legal_deepseek_flash.json
```
