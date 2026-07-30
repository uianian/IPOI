---
name: ipo-repo-deploy-and-audit
description: 部署胡禹成在 github.com/2471023025/competiontion/tree/main/ipo 上传的多智能体后端Demo到服务器，并对照赛题《基于多智能体协同的港股IPO招股书解析与上市后风险预警探索》的硬性要求，逐项审计现有实现的覆盖度与差距。当用户提到"部署""对齐胡禹成的代码""服务器上跑起来""这个demo符不符合赛题要求""还差什么"时使用本skill。
---

# 胡禹成 IPO Demo 部署与赛题对齐审计

本skill基于对仓库 `2471023025/competiontion` 的 `ipo/` 目录（README.md、
USAGE.md、spec.md、task.md、requirements.txt、configs/settings.yaml 等）
的实际拉取结果编写，仓库地址：
`https://github.com/2471023025/competiontion/tree/main/ipo`。

## 仓库现状速览（部署前先建立认知）

这是一个**纯后端 FastAPI + LangGraph 服务**，不含前端页面，架构：

```
src/
├── models/      核心数据模型（法务/财务/情绪/报告/追踪等Pydantic模型）
├── db/          PostgreSQL + SQLAlchemy(async) 持久化层
├── skills/      长文档检索 / 同行估值比对 / 现金流消耗测算 / 情绪热度打分
├── agents/      法务合规 / 财务穿透 / 市场情绪 / 总控决策 四个Agent
├── protocols/   辩论协议(≤3轮) + 跨模态融合(基本面0.65×情绪0.35)
├── graph/       LangGraph 状态图编排
├── llm/         vLLM/OpenAI/OpenRouter 兼容客户端
├── tracing/     推理链路审计日志
└── api/routes/  REST + WebSocket 接口
```

外部依赖：PostgreSQL 14+、Redis 6+、一个 OpenAI 兼容的 LLM/Embedding 服务
（vLLM 本地部署 或 OpenAI/DeepSeek/OpenRouter 等远程API）。

## 第0步：部署前必查（安全 + 一致性）

**⚠️ 安全问题（务必先处理，不要跳过）**：`ipo/configs/settings.yaml` 中
硬编码了一个可用的 OpenRouter API Key，且该仓库是公开仓库。部署前必须：
1. 到对应服务商后台**吊销/轮换**这个 key（无论现在是否已经被盗用，只要
   公开过就应视为已泄露）；
2. 用 `git filter-repo` 或 BFG Repo-Cleaner 清理 git 历史中的这个 key
   （只改当前文件不够，历史 commit 里仍能翻出来）；
3. 之后所有密钥改用环境变量（`IPO_LLM_API_KEY`）或 `.env`（加入
   `.gitignore`），不要再写进 `settings.yaml` 提交。

**配置一致性问题**：README.md 描述的默认方案是 vLLM 本地部署
`Qwen2.5-72B-Instruct`，但仓库里实际提交的 `configs/settings.yaml`
默认 `provider: openrouter`、`chat_model: google/gemma-4-31b-it:free`
（一个免费小模型）。部署前需要和胡禹成确认：这只是他本地调试时的临时配置，
还是团队计划就用免费模型跑？如果冲抵不清楚，直接照抄默认配置部署，
得到的推理质量会和README描述的预期（Qwen2.5-72B/GPT-4o级别）有明显落差，
影响后续抽取准确率评估的可信度。

## 第一步：服务器环境准备

```bash
# Python
python -V   # 需要 3.10+

# Docker（用于快速起 PostgreSQL / Redis，README推荐方式）
docker --version || curl -fsSL https://get.docker.com | sh
```

## 第二步：拉取代码、建虚拟环境、装依赖

```bash
git clone https://github.com/2471023025/competiontion.git
cd competiontion/ipo

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

注意 `requirements.txt` 里实际比 README 文档列出的多了
`sentence-transformers`、`modelscope`（用于本地 fallback embedding 模型），
部署时不要漏装，否则 `llm/client.py` 里 embedding 服务不可用时的降级路径会失败。

## 第三步：起外部依赖（PostgreSQL / Redis）

```bash
docker run -d --name ipo-postgres \
  -e POSTGRES_DB=ipo_risk -e POSTGRES_PASSWORD=<改成强密码，不要用README示例里的postgres> \
  -p 5432:5432 postgres:16

docker run -d --name ipo-redis -p 6379:6379 redis:7-alpine
```

服务器环境下建议加 `--restart unless-stopped`，并且**不要**把 5432/6379
端口直接暴露给公网（若服务器有公网IP，用 `-p 127.0.0.1:5432:5432` 只绑本地，
或用安全组/防火墙限制来源）。

## 第四步：配置 LLM

修改 `configs/settings.yaml`（或改用环境变量覆盖，更适合服务器部署，
避免密钥进配置文件）：

```bash
export IPO_LLM_PROVIDER="openai"          # 或 vllm / openrouter
export IPO_LLM_API_KEY="<新轮换的key，不要用泄露的那个>"
export IPO_LLM_API_BASE="https://api.openai.com/v1"
export IPO_LLM_CHAT_MODEL="gpt-4o"        # 或团队约定的实际模型
export IPO_DB_POSTGRES_URL="postgresql+asyncpg://postgres:<密码>@localhost:5432/ipo_risk"
export IPO_DB_REDIS_URL="redis://localhost:6379/0"
```

若走本地 vLLM，需要额外一台有GPU的机器/进程跑：

```bash
python -m vllm.entrypoints.openai.api_server --model Qwen2.5-72B-Instruct --port 8000
python -m vllm.entrypoints.openai.api_server --model BAAI/bge-large-zh-v1.5 --port 8001
```

## 第五步：初始化数据库、启动服务

```bash
python scripts/init_db.py
python scripts/run.py
```

验证：
- `curl http://<server>:8080/health`
- `curl http://<server>:8080/docs`（FastAPI自动文档，检查所有路由是否加载成功）
- `python scripts/run_example.py`（内置示例招股书文本，端到端跑一次，
  产出 `output_example.json`，是判断部署是否成功的最快方式）

## 第六步：生产化建议（服务器长期运行）

- 用 `systemd` 或 `supervisor` 托管 `scripts/run.py` 进程，不要用 `nohup` 裸跑；
- 反向代理（nginx）+ HTTPS，不要把 8080 端口原样暴露公网；
- `api.cors_origins: ["*"]`（settings.yaml默认值）在生产环境应收紧为
  前端实际域名，避免任意来源调用分析接口；
- 日志/追踪记录（`tracing/logger.py` 写入 PostgreSQL）建议做好定期备份，
  这是"推理链路100%可追踪"这一硬指标的证据来源，答辩/评审可能需要直接调取。

---

## 第七步：对照赛题要求的差距审计（核心）

逐项对照赛题文档（东吴证券命题）与胡禹成仓库 `spec.md`/`task.md` 的实际实现：

| 赛题要求 | 仓库现状 | 差距/建议 |
|---|---|---|
| 任务1：招股书PDF解析防幻觉 | `long_doc_retrieval/parser.py` 用 PyMuPDF + Unstructured 做文本层解析+语义分片 | 团队之前测试选定的是 **Infinity-Parser2 多模态版面解析模型**（能处理表格/OCR/扫描件，已跑通蜜雪冰城招股书558页）。PyMuPDF 是纯文字层提取，遇到扫描件、复杂/竖排表格大概率直接失效或效果远差于Infinity-Parser2。**需要和胡禹成确认**：这是backend先跑通流程用的占位实现，还是最终方案？若是最终方案，需要补一层"复杂版式检测→路由到Infinity-Parser2"的分支，否则任务1"防幻觉解析"这个核心攻关点在复杂样本上会明显达不到目标。 |
| 任务1：关键风险要素抽取准确率≥80%，证据召回率≥85% | `extractor.py` 有"抽取结果附置信度标记，无支撑标为低置信度"的设计，方向对；但**仓库里没有找到任何量化评测脚本或标注测试集** | 缺少可执行的评测流程。需要基于 `ipo-prospectus-dataset-analysis` 产出的标注样本，补一个 `tests/eval/` 脚本，跑出真实的准确率/召回率数字，而不是只在架构文档里写"验收条件"。这是当前离赛题硬指标最远的一块。 |
| 任务2：法务合规/财务穿透/市场情绪/总控决策四个Agent + Skill编排 | 四个Agent、四个核心Skill（长文档检索/同行估值比对/现金流消耗测算/情绪热度打分）均已按spec实现，LangGraph状态图编排、辩论协议(≤3轮)、跨模态融合(0.65/0.35)、Skill注册中心均有代码骨架 | 这是仓库里**完成度最高**的部分，和赛题任务2的要求高度对齐，包括"逻辑冲突→辩论→查证"链路。需要重点核查的是这些逻辑是否已经用真实招股书跑通过，还是仍停留在骨架/单测层面（`task.md` 第19-20节"集成与端到端联调""测试与验证"标的是 checkbox，需要问胡禹成实际打勾进度）。 |
| 任务2：推理链路/角色分工/工具调用/证据来源可追踪率100% | `tracing/logger.py` + `TraceRecord` 模型 + `GET /analysis/{task_id}/trace` 接口，设计上覆盖了这个要求 | 需要实测验证：拿一份真实招股书跑一遍，检查 trace 记录里是不是每一步都真的写进去了，还是部分Skill调用没有埋点导致链路有断点。 |
| 任务3：可解释预警报告，含风险诱因+证据+PDF页码段落映射 | `models/report.py` 有 `RiskFactorDetail`/`FusedRiskAssessment`/`RiskReport`，`EvidenceRef` 模型设计上带页码 | 报告结构设计合理，但**没有前端**（属于熊梓焱负责的任务3模块，需要熊梓焱基于 `GET /analysis/{task_id}/report` 和 WebSocket 进度接口去对接，参考 `ipo-agent-dashboard-ui` skill），也没有"截图/PDF区域高亮"这一层——目前只到页码级别，赛题要求"精准映射至招股书原PDF页码与段落的**证据截图**"，还需要基于解析阶段保留的 bbox 坐标补一层截图生成逻辑。 |
| 任务3/目标：结合上市首日/5日/20日/60日真实涨跌幅与破发数据验证预警效力，且5日内下跌需加权评价 | **仓库里完全没有找到这部分实现**：没有对接 `hksharedescription`/`hkcompanyinfo`/EOD行情三张表的代码，`spec.md` 第1.4节甚至明确写"本组件不负责实时行情推送"、市场情绪Agent只依赖抽象的"市场数据源"适配器占位 | 这是当前**最大的缺口**，且直接对应赛题里的一条硬性技术指标（"上市风险预警业务参考价值"，还专门要求对"5个交易日内显著下跌"给更高权重）。需要新增一个模块（对应团队文档里被划掉但赛题仍然要求的"上市后表现验证"），基于 `hk-market-data-toolkit` skill 里的三张表计算真实涨跌幅，回填进风险报告做验证，而不能只停留在架构设计阶段。 |
| 团队内部约定：风险等级 A/低风险 B/关注 C/高风险（项目`.md`文档里的口径） | 仓库 `fusion.py`/`settings.yaml` 用的是**五级制**（极低/低/中/高/极高，对应0-100分区间） | 两边口径不一致，需要团队内部拍板统一用哪套，否则前端（熊梓焱）和报告文案（马宝灵）会对不上。赛题原文没有强制要求几级，五级制信息量更大，可以考虑把项目文档也改成五级，而不是反过来削弱代码。 |
| 数据集：3-5年招股书PDF + 港股基本信息 + 历史行情三类数据 | 无任何针对赛题实际提供的 `hksharedescription.csv`/`hkcompanyinfo.csv`/EOD价格表的适配代码 | 需要新写一个数据适配层（`peer_comparison`/`sentiment` 里的 `market_adapter.py`、`peer_adapter.py` 目前应该还是占位/mock），接入真实CSV数据，这也是"上市后表现验证"缺口的前置依赖。 |
| 成果交付：可运行原型/API + 完整源码+环境配置 | README/USAGE文档质量高，`scripts/run_example.py` 提供了免数据库快速验证路径，`scripts/init_db.py`覆盖建表 | 基本满足"可直接部署运行"的交付要求，是这份Demo比较扎实的地方，部署流程清晰、依赖声明明确。 |

## 审计结论产出建议

审计完成后，建议产出一份简短的"差距清单+认领表"（谁来补哪一项、
预计工时），而不是只在对话里过一遍——尤其要把"上市后表现验证缺失"和
"抽取准确率/召回率没有量化评测"这两条标为**高优先级**，因为它们对应
赛题里明确写出来的硬性技术指标，评审大概率会直接对照打分。
