# IPO Insight 项目 — Claude Code Skills 规划

对应赛题：07东吴证券《基于多智能体协同的港股IPO招股书解析与上市后风险预警探索》

## 一、规划思路

赛题拆成 3 个攻关任务，团队 5 人按模块分工。每个人/模块日常重复做的事情
（解析规则、抽取标准、Agent 编排规范、报告模板、数据字典查询方式）都适合沉淀成
一个 **Claude Code Skill**，这样：

- 新成员或换机器时，Claude Code 一眼就能对齐团队已经踩过的坑（竖表、截断表格、
  换行丢失等 6 类解析异常已经在文档里记录了，不应该每次重新踩）；
- 输出格式（JSON schema、风险评分结构、报告模板）被固化，不同模块之间才能拼得上；
- 任务目标里的硬指标（抽取准确率≥80%、证据召回率≥85%、推理链路可追踪率100%）
  被写进 skill 里，Claude 每次执行都会对照检查，而不是写完就忘。

## 二、Skill 清单与责任人映射

| Skill 目录 | 对应任务/模块 | 主要负责人 | 何时触发 |
|---|---|---|---|
| `hk-ipo-pdf-parsing` | 任务1 / 模块1 PDF解析 | 吴倩倩、likesnow | 处理招股书PDF、调用Infinity-Parser2、遇到竖表/截断表/换行丢失等解析异常时 |
| `ipo-risk-feature-extraction` | 任务1 风险特征抽取 | 马宝灵（定标准）、吴倩倩（实现） | 从解析后的结构化文本中抽取财务指标与非标风险特征 |
| `ipo-risk-rag-retrieval` | 任务1 金融RAG检索 | 吴倩倩 | 需要"风险证据定位"（而非普通问答）、要求页码级证据溯源时 |
| `ipo-multi-agent-orchestration` | 任务2 多Agent协作 | 胡禹成 | 搭建/修改 法务合规、财务穿透、市场情绪、总控决策 四个Agent及编排逻辑 |
| `ipo-warning-report-generator` | 任务3 报告生成 | 熊梓焱、likesnow | 生成《IPO风险穿透预警报告》，需要证据截图+页码映射 |
| `hk-market-data-toolkit` | 数据集处理（全组共用） | 全员 | 查询/关联 hksharedescription、hkcompanyinfo、EOD行情三张表 |
| `ipo-agent-dashboard-ui` | 任务3 / 模块3 前端 | 熊梓焱 | 构建Agent协作过程展示页、风险报告页、PDF证据高亮UI |

## 三、按里程碑的使用顺序

1. **第一阶段（需求理解+环境，7.1-7.7）**：先用 `hk-market-data-toolkit`
   跑通数据集探索，确认字段含义；`hk-ipo-pdf-parsing` 先跑通最小 Demo（1份招股书）。
2. **第二阶段（RAG开发，7.8-7.20）**：`hk-ipo-pdf-parsing` → `ipo-risk-feature-extraction`
   → `ipo-risk-rag-retrieval` 三个 skill 串联，产出"输入招股书、输出可信风险回答"。
3. **第三阶段（Agent系统，7.21-8.5）**：`ipo-multi-agent-orchestration`，四个Agent
   都要调用前面两个 skill 的输出作为工具能力。
4. **第五阶段（系统封装，8.16-8.25）**：`ipo-warning-report-generator` +
   `ipo-agent-dashboard-ui` 把前面所有结果串成可运行原型/API。

## 四、安装方式

把 `skills/` 下每个子目录整体复制到项目仓库的 `.claude/skills/` 下即可，
Claude Code 会自动读取各目录里的 `SKILL.md`。例如：

```bash
cp -r skills/hk-ipo-pdf-parsing  your-repo/.claude/skills/
cp -r skills/ipo-risk-feature-extraction your-repo/.claude/skills/
cp -r skills/ipo-risk-rag-retrieval your-repo/.claude/skills/
cp -r skills/ipo-multi-agent-orchestration your-repo/.claude/skills/
cp -r skills/ipo-warning-report-generator your-repo/.claude/skills/
cp -r skills/hk-market-data-toolkit your-repo/.claude/skills/
cp -r skills/ipo-agent-dashboard-ui your-repo/.claude/skills/
```

## 五、后续维护建议

- 每次团队踩到新的解析/抽取异常（类似文档里记录的"竖着的表""换行丢失"），
  第一时间补进对应 skill 的 `references/` 而不是口头传达，避免下次重复踩坑。
- 硬指标（80%/85%/100%）如果后续和命题方沟通有调整，同步改 skill 描述里的数字，
  否则 Claude 会一直按旧指标自检。
