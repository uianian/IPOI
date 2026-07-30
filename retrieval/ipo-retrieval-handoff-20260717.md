# Handoff：港股 IPO 检索（独立工程）

**日期**：2026-07-17  
**工作区**：`/nfs/users/wuqianqian/IPOI/retrieval`（与 `agents/` 同级）  
**说明**：本目录由 `agents/ipo` 检索相关代码**复制**而来；`agents/` 原文件保留不动。

---

## 最短启动

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/retrieval
# 索引：本项目私有 .runtime/indexes
python scripts/simulate_agent_retrieval.py \
  --doc-id 136ee620-0473-450b-a566-72172824cdec \
  --agent all --issuer-type general --top-k 5 \
  --out .runtime/agent_retrieval_mixue.json
python scripts/analyze_retrieval_report.py \
  --result .runtime/agent_retrieval_mixue.json \
  --doc-name 蜜雪冰城 \
  --out .runtime/reports/retrieval_quality_mixue.md
```

API Key：`export IPO_LLM_API_KEY=...`（见 `configs/settings.yaml`）

---

## 架构现状

- 财务 2.1/2.2/2.3：`TBL_IS` / `TBL_BS` / `TBL_CF` 整表 Top-K（`recall_unit: table`）
- **通用策略（一份配置）**：`configs/finance_table_retrieval_strategy.md`
  + `configs/agent_retrieval_profiles.yaml`（综合/合并别名、行名门控、附录-only、跨页 pack）
- 法务：字段级 Grep∪BM25∪Vector
- 输出：`evidence_by_table` + `field_table_map` + `evidence_by_field`

## 关键路径

| 用途 | 路径 |
|------|------|
| 全流程图（文件/方法） | `docs/retrieval_pipeline.md` |
| 检索核心 | `src/retrieval/` |
| Agent 模拟 | `src/retrieval/agent_simulator.py` |
| 通用策略说明 | `configs/finance_table_retrieval_strategy.md` |
| 配置 | `configs/agent_retrieval_profiles.yaml` |
| 质量报告脚本 | `scripts/analyze_retrieval_report.py` |
| Skill | `IPOI/.cursor/skills/ipo-risk-rag-retrieval` |

## 下一步建议

1. 抽取层对接 `evidence_by_table`
2. 新样本回归：只改别名表，不新增公司专属 profile
3. 与 agents 双向同步策略（本仓为检索主开发区）

用中文与用户沟通。
