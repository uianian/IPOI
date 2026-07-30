# 多角色尽调Agent协作架构 — 编码任务规划

## 1. 项目骨架与基础设施搭建

- [ ] 初始化项目目录结构，创建 `src/`、`tests/`、`configs/`、`scripts/` 等顶层目录
- [ ] 创建 `pyproject.toml`，声明项目元数据与核心依赖（langgraph, fastapi, pydantic>=2.0, faiss-cpu, chromadb, pymupdf, unstructured, redis, sqlalchemy, asyncpg, uvicorn）
- [ ] 创建 `configs/settings.yaml`，定义系统级可配置参数（vLLM服务地址、向量检索参数、辩论最大轮次、跨模态融合权重、数据时效阈值等）
- [ ] 创建 `src/config.py`，使用 Pydantic Settings 加载配置文件，实现环境变量覆盖机制
- [ ] 创建 `src/main.py`，初始化 FastAPI 应用实例与生命周期管理（启动时初始化数据库连接池、Skill注册表、vLLM客户端）

## 2. 核心数据模型定义

- [ ] 创建 `src/models/enums.py`，实现所有核心枚举类型：`AgentRole`、`RiskLevel`、`MarketTemperature`、`SeverityLevel`、`ConflictType`、`DebateStance`、`StepType`、`ExecutionStatus`
- [ ] 创建 `src/models/evidence.py`，实现 `EvidenceRef` 证据引用模型
- [ ] 创建 `src/models/prospectus.py`，实现 `ProspectusDocument`、`DocumentChunk` 招股书文档模型
- [ ] 创建 `src/models/legal.py`，实现 `LegalRiskFeature`、`ComplianceFlaw`、`CrossReference`、`LegalAnalysisResult` 法务分析结果模型
- [ ] 创建 `src/models/finance.py`，实现 `FinancialIndicator`、`ValidationResult`、`ManipulationSignal`、`BurnRateResult`、`ComparisonResult`、`FinanceAnalysisResult` 财务分析结果模型
- [ ] 创建 `src/models/sentiment.py`，实现 `SentimentScore`、`MarketEvent`、`SectorLiquidity`、`SentimentResult` 市场情绪分析结果模型
- [ ] 创建 `src/models/conflict.py`，实现 `ConflictItem`、`DebateMessage`、`DebateRound` 冲突与辩论模型
- [ ] 创建 `src/models/report.py`，实现 `RiskFactorDetail`、`FusedRiskAssessment`、`RiskReport` 风险报告模型
- [ ] 创建 `src/models/trace.py`，实现 `TraceRecord`、`TraceSummary` 追踪审计模型
- [ ] 创建 `src/models/api.py`，实现 `APIResponse[T]` 统一响应格式、`AnalysisRequest`、`AnalysisTask`、`AnalysisStatus`、`HealthStatus` API模型
- [ ] 创建 `src/models/__init__.py`，统一导出所有模型，确保 Pydantic V2 类型校验通过

## 3. 数据库与持久化层

- [ ] 创建 `src/db/database.py`，使用 SQLAlchemy AsyncEngine 初始化 PostgreSQL 异步连接池
- [ ] 创建 `src/db/models.py`，定义 SQLAlchemy ORM 表结构（prospectus_documents, trace_records, skill_registrations, analysis_tasks, risk_reports）
- [ ] 创建 `src/db/migrations/` 目录与 Alembic 初始迁移脚本，创建所有数据表
- [ ] 创建 `src/db/repositories/trace_repo.py`，实现追踪记录的异步写入与按招股书ID/Agent角色/时间范围查询
- [ ] 创建 `src/db/repositories/skill_repo.py`，实现 Skill 注册信息的增删改查与版本管理
- [ ] 创建 `src/db/repositories/task_repo.py`，实现分析任务状态持久化与进度更新
- [ ] 创建 `src/cache/redis_client.py`，封装 Redis 异步客户端，实现市场数据缓存（24小时TTL）与分析进度缓存

## 4. Skill基类与Skill注册中心

- [ ] 创建 `src/skills/base.py`，实现 `BaseSkill` 抽象基类，定义 `skill_name`、`version`、`execute()`、`validate_input()`、`health_check()` 标准接口
- [ ] 创建 `src/skills/registry.py`，实现 `SkillRegistry` 注册中心：
  - `register_skill()`：注册新Skill，校验输入输出Schema完整性
  - `discover_skill()`：按名称与版本发现Skill
  - `check_health()`：定期调用各Skill的 `health_check()`，暴露系统级健康状态
  - `list_skills()`：查询所有已注册Skill及其版本信息
- [ ] 创建 `src/skills/models.py`，实现 `SkillRegistration`、`SkillInput`、`SkillOutput`、`VersionChange`、`HealthCheckResult` Skill注册相关模型

## 5. 长文档检索Skill（LongDocRetrievalSkill）

- [ ] 创建 `src/skills/long_doc_retrieval/parser.py`，实现 PDF 解析 Pipeline：
  - 使用 PyMuPDF 提取文本与页面映射
  - 使用 Unstructured 进行语义分段（段落边界 + 语义相似度混合分片，目标512 tokens/片）
  - 为每个分片生成元数据标签（页码、章节、段落类型）
- [ ] 创建 `src/skills/long_doc_retrieval/indexer.py`，实现向量化索引构建：
  - 调用 vLLM embedding 接口生成分片向量表示
  - 构建 FAISS 索引（IndexFlatIP 或 IVFFlat）
  - 将分片元数据写入 Chroma（支持元数据过滤）
- [ ] 创建 `src/skills/long_doc_retrieval/retriever.py`，实现混合检索策略：
  - 向量相似度检索（FAISS Top-K）
  - 元数据过滤（按章节类型、页码范围）
  - 关键词 BM25 检索 + RRF 融合排序
- [ ] 创建 `src/skills/long_doc_retrieval/extractor.py`，实现结构化信息抽取：
  - 调用 vLLM 进行结构化信息抽取
  - 每个抽取结果附带原文片段引用与置信度标记
  - 无原文支撑项标记为"低置信度"（幻觉抑制）
- [ ] 创建 `src/skills/long_doc_retrieval/skill.py`，整合解析、索引、检索、抽取为完整 Skill，实现 `index_document()`、`retrieve()`、`extract_structured()` 接口
- [ ] 处理异常场景：PDF解析失败时标记"不可解析"并通知用户；关键指标缺失时标记"数据缺失"

## 6. 同行估值比对Skill（PeerComparisonSkill）

- [ ] 创建 `src/skills/peer_comparison/peer_adapter.py`，实现同行数据库适配器，获取可比公司估值数据（PE/PB/PS/EV-EBITDA）
- [ ] 创建 `src/skills/peer_comparison/comparator.py`，实现估值比对核心逻辑：
  - 计算各指标的行业均值/中位数/标准差
  - 计算发行人指标与行业均值的Z-Score偏离度
  - 标注显著偏离项
- [ ] 创建 `src/skills/peer_comparison/skill.py`，整合为完整 Skill，实现 `compare_valuation()`、`get_peer_data()` 接口
- [ ] 处理异常场景：可用可比公司少于3家时，扩大行业范围搜索并标注"对标样本有限，结论可靠度降级"

## 7. 现金流消耗测算Skill（CashFlowCalculationSkill）

- [ ] 创建 `src/skills/cash_flow/calculator.py`，实现现金流消耗测算核心逻辑：
  - 现金流消耗率 = 经营性现金净流出 / 月份数
  - 资金耗尽时间 = 现金储备 / 现金流消耗率
  - 敏感性分析：乐观/中性/悲观三组假设下分别计算
- [ ] 创建 `src/skills/cash_flow/skill.py`，整合为完整 Skill，实现 `calculate_burn_rate()`、`estimate_runway()` 接口
- [ ] 处理异常场景：不同假设下消耗率差异超50%时，输出三组测算结果并标注敏感性分析结论

## 8. 情绪热度打分Skill（SentimentScoringSkill）

- [ ] 创建 `src/skills/sentiment_scoring/scorer.py`，实现多因子加权评分模型：
  - 大盘冷暖因子：基于指数走势、成交额变化、IPO首日涨跌统计映射至0-100
  - 板块流动性因子：基于日均成交额、换手率、资金净流入映射至0-100
  - 舆情热度因子：基于正负面新闻比例、社交媒体讨论量映射至0-100
  - IPO认购倍数因子：基于认购倍数映射至0-100
  - 默认权重：w1=0.3, w2=0.25, w3=0.25, w4=0.2（可配置）
- [ ] 创建 `src/skills/sentiment_scoring/decomposer.py`，实现因子贡献度分解，输出各因子评分与贡献度明细
- [ ] 创建 `src/skills/sentiment_scoring/skill.py`，整合为完整 Skill，实现 `calculate_score()`、`decompose_factors()` 接口
- [ ] 处理异常场景：核心市场数据时间戳超24小时标记"数据过期预警"；单日涨跌超5%触发极端行情模式，评分可靠度降级

## 9. 追踪审计记录器（TraceAuditLogger）

- [ ] 创建 `src/tracing/logger.py`，实现 `TraceAuditLogger`：
  - `log_step()`：异步写入追踪记录至 PostgreSQL，包含 trace_id、agent_role、skill_name、step_type、输入输出摘要、证据引用、时间戳、父级追踪ID
  - `query_trace()`：支持按招股书ID、Agent角色、时间范围查询追踪记录
  - `verify_evidence_chain()`：验证从结论到原始证据的完整链路，检测断链
- [ ] 创建 `src/tracing/context.py`，实现追踪上下文管理器，在Agent执行过程中自动注入 trace_id 与 parent_trace_id，确保推理链路树结构完整

## 10. vLLM 客户端封装

- [ ] 创建 `src/llm/client.py`，封装 vLLM 推理服务调用：
  - 文本生成接口（含重试机制，最多3次）
  - Embedding 接口（用于文档向量化）
  - 结构化输出接口（JSON Schema 约束输出格式）
- [ ] 创建 `src/llm/prompts.py`，定义各Agent的Prompt模板：
  - 法律风险特征抽取 Prompt
  - 财务指标抽取与校验 Prompt
  - 财务操纵特征识别 Prompt
  - 舆情事件提取 Prompt
  - 一致性验证 Prompt
  - 冲突描述生成 Prompt
- [ ] 处理异常场景：LLM调用超时时自动重试，3次失败后降级返回基础检索结果并标记"未完成深度分析"

## 11. 法务合规Agent（LegalAgent）

- [ ] 创建 `src/agents/legal/agent.py`，实现 `LegalAgent`：
  - 第一步：调用 `LongDocRetrievalSkill.retrieve()` 检索法律相关段落（诉讼、行政处罚、知识产权、VIE架构等关键词）
  - 第二步：调用 vLLM 进行法律风险特征抽取与严重程度分级（高危/中危/低危）
  - 第三步：对每个风险特征调用 `LongDocRetrievalSkill.retrieve()` 进行交叉引用检索，验证判断一致性
  - 第四步：证据回溯验证，标记无原文支撑的推断为"低置信度"
- [ ] 实现分级约束：高危风险判定必须关联至少一条具体法律条款或监管规定引用
- [ ] 实现二次扫描机制：法律风险信息散布在非法律章节时，触发全文档补充扫描
- [ ] 创建 `src/agents/legal/prompts.py`，定义法务分析专用Prompt模板（风险特征抽取、严重程度分级、交叉引用验证）
- [ ] 在每个关键步骤调用 `TraceAuditLogger.log_step()` 记录推理链路

## 12. 财务穿透Agent（FinanceAgent）

- [ ] 创建 `src/agents/finance/agent.py`，实现 `FinanceAgent`：
  - 第一步：调用 `LongDocRetrievalSkill.retrieve()` 检索财务报表段落
  - 第二步：调用 vLLM 进行标准化指标抽取与表内勾稽关系校验
  - 第三步：调用 `CashFlowCalculationSkill` 计算现金流消耗率与资金耗尽时间
  - 第四步：调用 `PeerComparisonSkill` 进行同行估值比对
  - 第五步：调用 vLLM 进行财务操纵特征识别
  - 第六步：综合至少两项以上交叉证据做出风险判定
- [ ] 实现财务指标校验逻辑：表内勾稽关系验证、跨期连续性验证、同行横向对比异常检测
- [ ] 实现现金流敏感性分析：输出乐观/中性/悲观三组假设下的测算结果
- [ ] 创建 `src/agents/finance/prompts.py`，定义财务分析专用Prompt模板（指标抽取、勾稽校验、操纵特征识别）
- [ ] 在每个关键步骤调用 `TraceAuditLogger.log_step()` 记录推理链路

## 13. 市场情绪Agent（SentimentAgent）

- [ ] 创建 `src/agents/sentiment/agent.py`，实现 `SentimentAgent`：
  - 第一步：从市场数据源获取大盘行情数据与板块流动性数据
  - 第二步：调用 `SentimentScoringSkill` 计算综合情绪热度评分（0-100分）
  - 第三步：调用 vLLM 进行舆情事件提取与影响评估
  - 第四步：按可配置时间间隔刷新情绪评分
- [ ] 实现数据时效性保障：核心市场数据时间戳距今不超过24小时，否则标记"数据过期预警"
- [ ] 实现极端行情处理：单日涨跌超5%触发极端行情模式，评分可靠度降级
- [ ] 创建 `src/agents/sentiment/prompts.py`，定义情绪分析专用Prompt模板（舆情事件提取、影响评估）
- [ ] 创建 `src/agents/sentiment/market_adapter.py`，实现市场数据源适配器，支持多种数据源接入
- [ ] 在每个关键步骤调用 `TraceAuditLogger.log_step()` 记录推理链路

## 14. 辩论协议（DebateProtocol）

- [ ] 创建 `src/protocols/debate.py`，实现 `DebateProtocol` 辩论协议：
  - `initiate_debate()`：生成冲突描述，分发给相关Agent
  - `evaluate_consensus()`：基于LLM辅助判断修正结论是否消除逻辑矛盾
  - `terminate_debate()`：3轮辩论后仍未一致时标记"不可调和冲突"
  - 辩论消息格式遵循 `DebateMessage` 模型
- [ ] 实现辩论轮次控制：最大3轮，每轮记录辩论内容、证据补充、结论修正
- [ ] 实现不可调和冲突处理：标记冲突、附带各方论据摘要、触发人工审核流程

## 15. 跨模态融合引擎（CrossModalFusion）

- [ ] 创建 `src/protocols/fusion.py`，实现 `CrossModalFusion` 跨模态融合引擎：
  - `align_features()`：将动态时序特征聚合为与基本面特征同维度的静态表示（最新快照 + 趋势方向）
  - `fuse_and_rate()`：加权融合计算综合风险评分（默认 α=0.65基本面, β=0.35市场情绪，可配置）
  - `explain_weights()`：输出基本面因子与市场情绪因子的权重、各因子原始评分与贡献度
- [ ] 实现综合风险评级映射：[0,20)→极低, [20,40)→低, [40,60)→中, [60,80)→高, [80,100]→极高
- [ ] 确保可解释性：输出中明确标注各因子权重与贡献度

## 16. 总控决策Agent与LangGraph状态图编排

- [ ] 创建 `src/agents/master/agent.py`，实现 `MasterOrchestrator` 总控决策Agent：
  - `decompose_task()`：将尽调请求分解为法务/财务/情绪三个并行子任务
  - `detect_conflicts()`：自动检测不同Agent分析结果之间的逻辑冲突（语义冲突 + 背离冲突）
  - `orchestrate_debate()`：调度辩论协议处理逻辑冲突
  - `fuse_results()`：调用跨模态融合引擎汇总最终结论
- [ ] 创建 `src/graph/state.py`，定义 LangGraph `AgentState` TypedDict（prospectus_id, sub_tasks, legal_result, finance_result, sentiment_result, conflicts, debate_rounds, fused_result, final_report, trace_log）
- [ ] 创建 `src/graph/nodes.py`，实现各节点函数：
  - `task_decomposition_node`：任务分解节点
  - `legal_analysis_node`：法务分析节点
  - `finance_analysis_node`：财务分析节点
  - `sentiment_analysis_node`：情绪分析节点
  - `conflict_detection_node`：冲突检测节点
  - `debate_round_node`：辩论轮次节点
  - `cross_modal_fusion_node`：跨模态融合节点
  - `report_generation_node`：报告生成节点
- [ ] 创建 `src/graph/edges.py`，实现条件路由：
  - `has_conflict`：冲突检测后的路由（有冲突→辩论，无冲突→融合）
  - `debate_resolved`：辩论后的终止判定路由（已解决→融合，未解决且轮次<3→继续辩论，轮次=3→不可调和冲突→融合）
- [ ] 创建 `src/graph/builder.py`，组装 LangGraph `StateGraph`：注册所有节点与边，构建完整状态图
- [ ] 实现并行分析：法务/财务/情绪三个分析节点并行启动（LangGraph fan-out）
- [ ] 实现冲突检测算法：预定义冲突规则表 + LLM辅助判断相结合

## 17. REST API 层

- [ ] 创建 `src/api/routes/analysis.py`，实现尽调分析接口：
  - `POST /api/v1/analysis/submit`：提交尽调分析请求，返回任务ID
  - `GET /api/v1/analysis/{task_id}/status`：查询分析状态
  - `GET /api/v1/analysis/{task_id}/report`：获取风险报告
  - `GET /api/v1/analysis/{task_id}/trace`：获取推理链路
  - `GET /api/v1/analysis/{task_id}/conflicts`：获取冲突记录
- [ ] 创建 `src/api/routes/system.py`，实现系统管理接口：
  - `GET /api/v1/health`：系统健康检查（包含各Agent与Skill就绪状态）
  - `GET /api/v1/skills`：查询已注册Skill列表
  - `GET /api/v1/skills/{skill_name}/versions`：查询Skill版本
  - `POST /api/v1/skills/register`：注册新Skill
- [ ] 创建 `src/api/routes/websocket.py`，实现 WebSocket 进度推送端点：
  - `/ws/v1/analysis/{task_id}/progress`：实时分析进度通知
- [ ] 创建 `src/api/middleware.py`，实现访问控制中间件（仅授权人员可查看招股书原文与分析结论）
- [ ] 创建 `src/api/error_handlers.py`，实现统一异常处理与错误响应格式

## 18. Agent基类与通用机制

- [ ] 创建 `src/agents/base.py`，实现 `BaseAgent` 基类：
  - 统一的 Skill 调用接口（通过 SkillRegistry 动态发现）
  - 统一的追踪记录注入（自动调用 TraceAuditLogger）
  - 统一的 LLM 调用接口（通过 vLLM 客户端，含重试机制）
  - 统一的异常处理与降级模式切换
- [ ] 创建 `src/agents/message_bus.py`，实现Agent间结构化消息传递（基于 LangGraph State 的共享状态通信）

## 19. 集成与端到端联调

- [ ] 将四个核心 Skill 注册至 SkillRegistry，验证注册/发现/健康检查流程
- [ ] 将各 Agent 接入 LangGraph 状态图，验证任务分解→并行分析→冲突检测→辩论→融合→报告生成的完整链路
- [ ] 实现端到端流程测试：上传示例招股书PDF → 触发完整尽调Pipeline → 验证风险报告输出与推理链路完整性
- [ ] 验证并行分析性能：确认法务/财务/情绪三个Agent可并行执行
- [ ] 验证冲突检测与辩论机制：构造法务与财务结论矛盾场景，验证辩论轮次与终止逻辑
- [ ] 验证跨模态融合输出可解释性：确认输出包含各因子权重与贡献度

## 20. 测试与验证

- [ ] 编写 `tests/unit/models/` 目录下所有数据模型的单元测试，验证 Pydantic 类型校验与序列化
- [ ] 编写 `tests/unit/skills/` 目录下各 Skill 的单元测试：
  - LongDocRetrievalSkill：验证分片、索引、检索、抽取流程
  - PeerComparisonSkill：验证比对计算与偏离度标注
  - CashFlowCalculationSkill：验证消耗率计算与敏感性分析
  - SentimentScoringSkill：验证多因子评分与贡献度分解
- [ ] 编写 `tests/unit/agents/` 目录下各 Agent 的单元测试，验证分析流程与分级约束
- [ ] 编写 `tests/unit/protocols/` 目录下辩论协议与跨模态融合的单元测试
- [ ] 编写 `tests/integration/` 目录下集成测试：
  - 完整尽调Pipeline端到端测试
  - 冲突检测与辩论链路测试
  - Skill注册/发现/版本管理测试
  - 追踪审计链路完整性验证测试
- [ ] 编写 `tests/integration/api/` 目录下 API 接口测试，验证所有 REST 端点与 WebSocket 推送
- [ ] 性能验证：单份招股书完整尽调端到端处理时间不超过30分钟；单个Skill调用不超过60秒；索引构建不超过5分钟
- [ ] 可靠性验证：推理链路可追踪率100%；LLM调用失败自动重试；故障时保留已完成结果并标记故障环节
