
# 港股IPO多智能体风险预警系统 — 部署与运行指南

## 1. 环境要求

| 项目 | 最低版本 |
|------|---------|
| Python | 3.10+ |
| PostgreSQL | 14+ |
| Redis | 6.0+ |
| vLLM 推理服务 | 0.4+（或任意 OpenAI 兼容 API） |

## 2. 安装步骤

### 2.1 创建虚拟环境

```bash
conda create -n ipo-risk python=3.10 -y
conda activate ipo-risk
```

或使用 venv：

```bash
python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate      # Windows
```

### 2.2 安装依赖

```bash
pip install -r requirements.txt
```

> 如需 GPU 加速向量检索，将 `faiss-cpu` 替换为 `faiss-gpu`。

### 2.3 启动外部服务

**PostgreSQL：**

```bash
# Docker 方式（推荐）
docker run -d --name ipo-postgres \
  -e POSTGRES_DB=ipo_risk \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:16

# 初始化数据表
cd scripts
python init_db.py
```

**Redis：**

```bash
docker run -d --name ipo-redis \
  -p 6379:6379 \
  redis:7-alpine
```

**vLLM 推理服务：**

```bash
# 启动 Chat 模型服务
python -m vllm.entrypoints.openai.api_server \
  --model Qwen2.5-72B-Instruct \
  --port 8000

# 启动 Embedding 模型服务（另一端口）
python -m vllm.entrypoints.openai.api_server \
  --model BAAI/bge-large-zh-v1.5 \
  --port 8001
```

> 也可使用任何 OpenAI 兼容 API（如 Ollama、Text Generation Inference 等），在 `configs/settings.yaml` 中修改 `llm.vllm_base_url` 即可。

### 2.4 修改配置

编辑 `configs/settings.yaml`，确认以下配置与你的环境一致：

```yaml
llm:
  vllm_base_url: "http://localhost:8000/v1"   # vLLM 服务地址
  chat_model: "Qwen2.5-72B-Instruct"          # 对话模型
  embedding_model: "BAAI/bge-large-zh-v1.5"   # 向量模型

database:
  postgres_url: "postgresql+asyncpg://postgres:postgres@localhost:5432/ipo_risk"
  redis_url: "redis://localhost:6379/0"
```

也可通过环境变量覆盖（前缀 `IPO_`），例如：

```bash
export IPO_LLM_VLLM_BASE_URL="http://192.168.1.100:8000/v1"
export IPO_DB_POSTGRES_URL="postgresql+asyncpg://user:pass@db-host:5432/ipo_risk"
```

## 3. 初始化数据库

```bash
python scripts/init_db.py
```

该脚本会创建所有必要的数据表（prospectus_documents, trace_records, skill_registrations, analysis_tasks, risk_reports）。

## 4. 启动服务

```bash
python scripts/run.py
```

服务启动后访问：
- API 文档：http://localhost:8080/docs
- 健康检查：http://localhost:8080/health

## 5. 运行测试

```bash
# 全部单元测试
pytest tests/unit/ -v

# 仅模型测试
pytest tests/unit/models/ -v

# 仅 Skill 测试
pytest tests/unit/skills/ -v

# 仅协议测试
pytest tests/unit/protocols/ -v
```

## 6. API 使用示例

### 6.1 提交分析任务

```bash
curl -X POST http://localhost:8080/api/v1/analysis/submit \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/data/prospectus/example.pdf",
    "company_name": "示例公司",
    "stock_code": "01234",
    "options": {
      "industry": "生物科技"
    }
  }'
```

返回：

```json
{
  "success": true,
  "data": {
    "task_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "doc_id": "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy",
    "status": "pending"
  }
}
```

### 6.2 查询分析状态

```bash
curl http://localhost:8080/api/v1/analysis/{task_id}/status
```

### 6.3 获取风险报告

```bash
curl http://localhost:8080/api/v1/analysis/{task_id}/report
```

### 6.4 获取推理链路

```bash
curl http://localhost:8080/api/v1/analysis/{task_id}/trace
```

### 6.5 系统健康检查

```bash
curl http://localhost:8080/api/v1/health
```

### 6.6 查看已注册 Skill

```bash
curl http://localhost:8080/api/v1/skills
```

## 7. 项目结构

```
src/
├── config.py                    # Pydantic Settings 配置
├── main.py                      # FastAPI 入口
├── models/                      # 核心数据模型
│   ├── enums.py                 # 枚举定义
│   ├── evidence.py              # 证据引用模型
│   ├── prospectus.py            # 招股书文档模型
│   ├── legal.py                 # 法务分析结果模型
│   ├── finance.py               # 财务分析结果模型
│   ├── sentiment.py             # 市场情绪模型
│   ├── conflict.py              # 冲突与辩论模型
│   ├── report.py                # 风险报告模型
│   ├── trace.py                 # 追踪审计模型
│   └── api.py                   # API 请求/响应模型
├── db/                          # 数据库层
│   ├── database.py              # SQLAlchemy 异步引擎
│   ├── models.py                # ORM 表结构
│   └── repositories/            # 数据仓库
├── skills/                      # Skill 层
│   ├── base.py                  # Skill 抽象基类
│   ├── registry.py              # Skill 注册中心
│   ├── long_doc_retrieval/      # 长文档检索
│   ├── peer_comparison/         # 同行估值比对
│   ├── cash_flow/               # 现金流消耗测算
│   └── sentiment_scoring/       # 情绪热度打分
├── agents/                      # Agent 层
│   ├── base.py                  # Agent 抽象基类
│   ├── legal/                   # 法务合规 Agent
│   ├── finance/                 # 财务穿透 Agent
│   ├── sentiment/               # 市场情绪 Agent
│   └── master/                  # 总控决策 Agent
├── protocols/                   # 协议层
│   ├── debate.py                # 辩论协议（≤3轮）
│   └── fusion.py                # 跨模态融合引擎
├── graph/                       # LangGraph 编排
│   ├── state.py                 # AgentState 定义
│   ├── nodes.py                 # 节点函数
│   ├── edges.py                 # 条件路由
│   └── builder.py               # 状态图构建
├── llm/                         # LLM 客户端
│   ├── client.py                # vLLM 封装（含重试）
│   └── prompts.py               # Prompt 模板库
├── tracing/                     # 追踪审计
│   └── logger.py                # TraceAuditLogger
├── cache/                       # 缓存层
│   └── redis_client.py          # Redis 异步客户端
└── api/routes/                  # API 路由
    ├── analysis.py              # 分析接口
    ├── system.py                # 系统管理接口
    └── websocket.py             # WebSocket 进度推送
```

## 8. 核心流程

```
输入招股书PDF
    │
    ▼
[长文档检索Skill] → PDF解析 → 分片 → FAISS+BM25索引 → 混合检索
    │
    ▼
[任务分解] ──→ 法务Agent ──→ 财务Agent ──→ 情绪Agent  （并行）
    │              │              │              │
    │              ▼              ▼              ▼
    │         风险抽取       指标抽取+校验    情绪评分
    │              │              │              │
    ▼◀─────────────┴──────────────┴──────────────┘
    │
[冲突检测] ──有冲突──→ [辩论协议]（≤3轮）──→ 回到冲突检测
    │                        │
    │无冲突                   │不可调和
    ▼                        ▼
[跨模态融合] ←─── 基本面(0.65) × 市场情绪(0.35)
    │
    ▼
[风险报告生成] → 五级风险评级 + 因子贡献度 + 证据溯源
```

## 9. 最小可运行配置（无需 PostgreSQL/Redis）

如果只想快速验证核心逻辑，可以只启动 vLLM 服务（或使用远程 API），系统会在数据库连接失败时降级运行，核心的 Skill 和 Agent 逻辑仍可工作。

## 10. 依赖清单

| 包名 | 用途 |
|------|------|
| pydantic | 数据模型校验 |
| pydantic-settings | 配置管理 |
| pyyaml | YAML 配置文件解析 |
| langgraph | 多Agent状态图编排 |
| langchain-core | LangChain 基础抽象 |
| httpx | vLLM API 异步调用 |
| fastapi | REST API 框架 |
| uvicorn | ASGI 服务器 |
| pymupdf | PDF 解析 |
| faiss-cpu | 向量相似度检索 |
| rank-bm25 | BM25 关键词检索 |
| sqlalchemy | ORM + 数据库操作 |
| asyncpg | PostgreSQL 异步驱动 |
| redis | 缓存 |
| alembic | 数据库迁移 |
| numpy | 数值计算 |
| typing-extensions | 类型扩展 |