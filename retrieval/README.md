# IPO Retrieval — standalone package (sibling of agents/)

从 `agents/ipo` **复制**出的港股招股书检索工程，用于单独开发/评测检索。
`agents/` 下原文件**未删除、未修改**。

## 目录

```
retrieval/
  configs/          # profiles / Grep 词表 / settings
  scripts/          # 建索引 / 模拟 Agent 召回 / 质量报告
  src/
    retrieval/      # FAISS + Grep∪BM25∪Vector + Agent 模拟
    llm/            # embedding 客户端（含本地 fallback）
    models/         # DocumentChunk
    config.py
  .runtime/
    indexes/   # 本项目私有 FAISS 索引（见 configs/settings.yaml → index_root）
    reports/
```

## 环境

与 agents 共用 conda 环境即可（已含 faiss / jieba / sentence-transformers）：

```bash
conda activate ipo-risk
cd /nfs/users/wuqianqian/IPOI/retrieval
# 如需新建环境：
# pip install -r requirements.txt
```

API Key（OpenRouter/OpenAI）请用环境变量，勿写入 Git：

```bash
export IPO_LLM_API_KEY="sk-..."   # 或 OPENAI_API_KEY
```

远程 embedding 不可用时会自动走本地 `bge-small-zh-v1.5`（与 agents 相同缓存目录）。

## 常用命令

```bash
cd /nfs/users/wuqianqian/IPOI/retrieval

# 1) 建索引（写入本项目 .runtime/indexes；mixue 已有一份私有副本时可跳过）
python scripts/build_index_from_parse.py \
  --parse ../pdf_parsing/output/mixue/full_parse.json \
  --company-name 蜜雪冰城 --stock-code 02097 --listing-date 2025-03-03 \
  --doc-id 136ee620-0473-450b-a566-72172824cdec

# 2) 财务+法务 Agent 检索模拟
python scripts/simulate_agent_retrieval.py \
  --doc-id 136ee620-0473-450b-a566-72172824cdec \
  --agent all --issuer-type general --top-k 5 \
  --out .runtime/agent_retrieval_mixue.json

# 3) 生成质量报告（MD，整表可渲染）
python scripts/analyze_retrieval_report.py \
  --result .runtime/agent_retrieval_mixue.json \
  --doc-name 蜜雪冰城 \
  --out .runtime/reports/retrieval_quality_mixue.md
```

## 内部 HTTP 服务（端口 9101）

分析启动前自动「建索引 + 财务/法务检索包」。**不对前端开放**；由专家解析服务在解析 **READY 后自动** `POST /internal/retrieval/prepare`。前端轮询 **9100** 的 `GET /api/v1/projects/:clientProjectId/index-status`（契约 v3.2 §6.5），`ready` 后才调 `analysis/start`。

- 设计文档：[`docs/retrieval_api_design.md`](docs/retrieval_api_design.md)
- 启动：`./scripts/start_retrieval_service.sh`（默认 `0.0.0.0:9101`，机房放行 9100–9200）
- 主路径：`POST /internal/retrieval/prepare` → 轮询 progress → `GET .../docs/{taskId}/artifacts`
- 后端固化调参：`FORCE_REBUILD` / `PREPARE_AGENTS` / `PACKAGE_TOP_K`（见 `service/config.py`）
- 索引键：解析 `taskId`（不是 `clientProjectId`）

德合冒烟（CLI，`taskId=dehe`）：

```bash
python scripts/build_index_from_parse.py \
  --parse ../pdf_parsing/output/samples_batch/00368_30-06-2020_德合集團_股份發售-reparse/00368_30-06-2020_德合集團_股份發售/full_parse.json \
  --company-name 德合集團 --stock-code 00368 --listing-date 20200630 \
  --doc-id dehe --force
python scripts/simulate_agent_retrieval.py --doc-id dehe --agent finance --issuer-type general --top-k 5 \
  --out .runtime/agent_retrieval_dehe_finance.json
python scripts/simulate_agent_retrieval.py --doc-id dehe --agent legal --issuer-type general --top-k 5 \
  --out .runtime/agent_retrieval_dehe_legal.json
```

## 与 agents 的关系

| 项 | 说明 |
|----|------|
| 代码 | 本目录独立维护；改这里不会自动同步回 agents |
| 索引 | 私有目录 `retrieval/.runtime/indexes`（`settings.yaml` → `index_root`），与 agents 隔离 |
| 配置 | `agent_retrieval_profiles.yaml` / `grep_lexicon.yaml` 已复制，可在本目录自由改 |
| Skill | 工作区 skill：`IPOI/.cursor/skills/ipo-risk-rag-retrieval` |

## 架构要点

- 财务 2.1/2.2/2.3：`recall_unit: table`，按 `TBL_IS` / `TBL_BS` / `TBL_CF` 整表 Top-K
- 法务：按字段 Grep∪BM25∪Vector Top-K
- 融合：加权 RRF；详见 `src/retrieval/hybrid.py`
