---
name: ipo-multi-agent-orchestration
description: 搭建和维护港股IPO风险预警的多智能体协作架构——法务合规Agent、财务穿透Agent、市场情绪Agent、总控决策Agent，基于LangGraph/AutoGen实现"推理-行动-观察-反思"编排，并保证100%推理链路可追踪。当用户提到"多Agent架构""Agent编排""LangGraph""AutoGen""总控决策""Skill封装""推理日志"，或需要新增/修改某个Agent角色时使用本skill。
---

# 港股IPO多智能体协作架构

对应赛题任务2（负责人：胡禹成主导，马宝灵/likesnow协作定义Agent能力范围）。

## 架构总览

```
招股书PDF + 股票代码
    ↓
金融文档解析RAG (hk-ipo-pdf-parsing + ipo-risk-feature-extraction)
    ↓
多Agent协同分析
  ├── 法务合规Agent
  ├── 财务穿透Agent
  ├── 市场情绪Agent
    ↓
风险融合总控决策Agent
    ↓
IPO风险报告（ipo-warning-report-generator）
```

## 四个Agent的职责边界（新增/修改Agent时务必先核对，避免职责重叠）

### 1. 法务合规Agent
- 发现：关联交易、股权结构风险、对赌协议、监管风险
- 能力组合：RAG检索（`ipo-risk-rag-retrieval`）+ 规则库（法规/监管条款硬规则）
  + LLM推理
- 输出应为结构化风险点列表，每条附证据页码，不输出笼统评分（评分留给总控）

### 2. 财务穿透Agent
- 分析：盈亏情况、现金流、毛利率、负债、融资依赖
- 输出格式示例：
  ```
  财务风险评分：78/100
  主要原因：
  1. 连续亏损
  2. 现金消耗速度高
  3. 研发投入不可持续
  ```
- 评分需可解释——每个扣分项必须能对应到具体财务指标数值，不能是黑箱打分

### 3. 市场情绪Agent
- 分析：恒生指数走势、行业热度、新股情绪、同板块历史破发率
- 核心难点：**跨模态融合**——招股书基本面是低频静态文本特征，市场环境是
  高频动态时序特征，二者时间尺度不同，融合时需先对齐到同一时间窗口
  （如"发行定价日前后N日的指数/板块涨跌幅"），不能简单拼接特征向量
- 输出格式示例：
  ```
  市场环境风险：高
  原因：港股科技板块流动性下降
  ```
- 数据来源参考 `hk-market-data-toolkit`（历史行情、上市信息）

### 4. 总控决策Agent
- 输入：上述三个Agent的结果
- 流程：冲突检测 → 证据复核 → 风险等级生成
- 冲突检测示例：财务Agent认为"低风险"但法务Agent发现严重对赌条款时，
  不能简单取平均分，应触发"辩论/查证链路"——让冲突的两个Agent各自补充证据，
  总控基于证据强度而非投票多数做最终判断
- 输出风险等级：A级(低风险) / B级(关注) / C级(高风险)

## 编排实现建议

- 框架：LangGraph（状态机式编排，适合本场景明确的"三个专家Agent并行→总控汇总"
  流程）或 AutoGen（更适合需要多轮辩论的场景）。若冲突检测环节需要多轮辩论，
  优先AutoGen风格的对话式编排；若流程相对固定，LangGraph的图结构更易维护和追踪。
- Skill封装：把"长文档检索""同行估值比对""现金流消耗测算""情绪热度打分"等
  能力封装成可复用的工具（Tool/Skill），供不同Agent调用，而不是在每个Agent
  内部重复实现一遍。
- 依赖参考：`references/env_deps.md` 中列出的Python依赖版本（langgraph、
  langchain-core、fastapi、pymupdf、faiss-cpu、rank-bm25等）。

## 硬指标自检：100%可追踪率

每一次Agent推理，日志必须记录：
1. 该Agent为什么做出这个判断（推理过程摘要）
2. 引用了哪些证据（页码+片段，来自`ipo-risk-rag-retrieval`）
3. 调用了哪些工具/Skill
4. 若涉及总控决策，冲突检测/辩论的完整过程

日志建议结构化存储（JSON lines，每条记录含 `agent_name`、`timestamp`、
`reasoning`、`evidence_refs`、`tool_calls`），而不是只存最终自然语言结论——
否则"逻辑解释有效性"评审时无法还原推理链条。

## 参考文件

- `references/env_deps.md` — 环境依赖版本清单
