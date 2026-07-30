# Handoff：港股 IPO 检索质量迭代（mixue）

**日期**：2026-07-17  
**工作区**：`/nfs/users/wuqianqian/IPOI`  
**下一会话建议焦点**：主表白名单过滤（压附注宽表噪声）/ 抽取层对接 `evidence_by_table` + `field_table_map`

---

## 1. 目标与当前位置

赛题检索侧目标：给定财务/风险字段，召回可抽数的招股书证据（页码 + text/table），不是通用问答 RAG。

**当前状态（2026-07-17 下午更新）**：

- FAISS + 三路混合检索已通。
- **财务 2.1/2.2/2.3 已改为按表类型整表 Top-K 召回**（`TBL_IS` / `TBL_BS` / `TBL_CF`），不再按指标 Top-K + 行名切片。
- 输出：`evidence_by_table` + `field_table_map`（字段→所属主表）；整表 HTML 进 `excerpt`。
- **尚未**：主表白名单压附注、抽取终值逻辑。

验证样本：`pdf_parsing/output/mixue`，`doc_id=136ee620-0473-450b-a566-72172824cdec`。

---

## 2. 本会话已完成

### 2.1 检索策略落地

| 能力 | 实现 |
|------|------|
| 表类型召回 | `recall_unit: table`；三张主表各 Top-K；`covers_fields` 映射指标 |
| 整表返回 | table 类 hit 的 `excerpt` 为完整表 HTML（上限 50k） |
| 邻接展开 | `expand_anchor`：找表或同页停；整表模式下丢弃未展开到 table 的 title |
| 章节角色 | `summary` / `discussion` / `appendix` / `other` 排序加权仍保留 |
| 词表 | `configs/agent_retrieval_profiles.yaml`：2.1–2.3 改为 `TBL_*`；去掉字段级 `row_labels` |

mixue 试跑页码（Top-5）：

- **TBL_IS**：428, 429, 487, 27, 327
- **TBL_BS**：488, 441, 477, 28, 27（488/477 可能仍有附注噪声）
- **TBL_CF**：437, 494, 440, 482, 29

### 2.2 汇报产物

- 报告：`agents/ipo/.runtime/reports/retrieval_quality_mixue.md`（MD 即可，勿默认出丑 PDF）
- 最新 JSON：`agents/ipo/.runtime/agent_retrieval_mixue.json`

---

## 3. 关键路径速查

| 用途 | 路径 |
|------|------|
| 特征定义 | `dataset/招股书关键信息抽取与风险特征定义.md` |
| 解析产物 | `pdf_parsing/output/mixue/full_parse.json` |
| FAISS 索引 | `agents/ipo/.runtime/indexes/136ee620-0473-450b-a566-72172824cdec/` |
| 检索配置 | `agents/ipo/configs/agent_retrieval_profiles.yaml` |
| 展开/角色 | `agents/ipo/src/retrieval/evidence_expand.py` |
| Agent 模拟 | `agents/ipo/src/retrieval/agent_simulator.py` |
| 最新召回 JSON | `agents/ipo/.runtime/agent_retrieval_mixue.json` |
| 质量报告 | `agents/ipo/.runtime/reports/retrieval_quality_mixue.md` |

相关 skills：`ipo-risk-rag-retrieval`（已写明整表策略）、`ipo-risk-feature-extraction`、`hk-ipo-pdf-parsing`。

---

## 4. 架构共识

1. **table_caption 不可信** → 定位靠 text + table + title 导航。  
2. **2.1/2.2/2.3 召回单元是表不是字段**；指标在表内，抽数在下游。  
3. **概要 vs 附录**：概要交叉校验；附录终值优先。  
4. 下一刀：**主表白名单**（表名/title_hints 同页共现）压附注宽表。

---

## 5. 未做 / 下一步

1. **P0**：主表白名单 + 降噪（TBL_BS 的 488/477 类附注）。  
2. **P0**：抽取层读 `evidence_by_table`，按 `field_table_map` 抽字段。  
3. **P1**：`CV_PREF` / `ADJ_NET` 无科目或非主表 → 低置信/空，勿硬凑。  
4. **P2**：10–20 家人工标注页码集。  
5. OpenRouter embeddings 仍 403 → 本地 `bge-small-zh-v1.5` fallback。

---

## 6. 红线

- 勿把 settings / API Key 写入文档或 Git。  
- 风险等级五级未与特征文档 A/B/C 统一，勿擅自改口径。  
- 非生物科技默认 skip 2.4 / 3.5（`--issuer-type general`）。  
- 勿 force-push；未要求不主动 commit。

---

## 7. Suggested skills

1. **`ipo-risk-rag-retrieval`** — 继续改检索时必用。  
2. **`ipo-risk-feature-extraction`** — 转入「抽数/字段落库」。  
3. **`hk-ipo-pdf-parsing`** — 仅当怀疑 `full_parse.json` 表结构异常。  

---

## 8. 给下一 agent 的最短启动

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/agents/ipo
python scripts/simulate_agent_retrieval.py --doc-id 136ee620-0473-450b-a566-72172824cdec \
  --agent all --issuer-type general --top-k 5 --out .runtime/agent_retrieval_mixue.json
python scripts/analyze_retrieval_report.py \
  --result .runtime/agent_retrieval_mixue.json \
  --out .runtime/reports/retrieval_quality_mixue.md
```

用中文与用户沟通。
