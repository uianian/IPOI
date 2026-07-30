---
name: ipo-agent-dashboard-ui
description: 构建IPO风险预警系统的Web交互界面——上传页（招股书PDF+股票代码）、Agent协作过程展示页（四个Agent实时分析状态）、风险报告页（综合评分+风险来源+PDF证据高亮溯源）。当用户提到"前端界面""Agent交互界面""证据高亮""上传页面""可视化""API服务接口"这类和任务3前端相关的需求时使用本skill。
---

# IPO风险预警 Web 前端

对应赛题任务3 / 项目模块3（负责人：熊梓焱），使用 `frontend-design` skill
中的设计规范来保证视觉质量，本skill只定义业务页面结构与数据契约。

## 三个核心页面

### 1. 上传页
输入：招股书PDF + 股票代码。
提交后应立即展示"已提交，Agent正在分析"的过渡态，不要让用户面对空白等待，
因为解析+多Agent分析全流程耗时可能较长（参考：单份招股书PDF解析约1min/页，
数百页文档解析本身就要数十分钟）。

### 2. Agent协作页面
实时/轮询展示四个Agent的状态机：
```
财务Agent:  分析中... / 完成
法务Agent:  分析中... / 完成
市场Agent:  分析中... / 完成
总控Agent:  等待前三者完成 → 冲突检测中 → 完成
```
数据源：`ipo-multi-agent-orchestration` 产出的结构化推理日志
（`agent_name`/`timestamp`/`reasoning`/`evidence_refs`/`tool_calls`）。
建议把每个Agent的推理过程做成可展开的时间线，满足"推理链路100%可追踪"要求，
而不是只显示一个进度条。

### 3. 风险报告页
展示 `ipo-warning-report-generator` 产出的报告JSON：
```
综合风险评分：75/100 — 高风险

风险来源：
① 现金流压力
② 客户集中
③ 市场情绪恶化

证据：PDF 第123页  ← 点击后需定位并高亮原PDF对应区域
```

**PDF证据高亮溯源**是本页面的核心交互难点：需要根据
`hk-ipo-pdf-parsing` 输出的 `bbox` 坐标，在前端PDF viewer中把对应区域
高亮框选出来，而不是只跳转到页码——纯跳页对"精准映射至原PDF页码与段落"
这一要求来说不够精确。

## 数据契约（前端依赖的后端接口，需与其他模块负责人对齐字段名）

- `POST /analyze`：入参 `{pdf_file, stock_code}`，返回 `{task_id}`
- `GET /analyze/{task_id}/status`：返回四个Agent各自状态（轮询用）
- `GET /analyze/{task_id}/report`：返回最终报告JSON（对接
  `ipo-warning-report-generator` 的机器可读版本）
- `GET /evidence?page=123&bbox=...`：返回原PDF该区域的截图或高亮渲染

若后端接口字段与上面不一致，应第一时间同步更新本skill，保持前后端契约文档
唯一可信来源，避免口头对接导致联调返工。

## 可复用性要求

赛题要求"可运行的原型系统或API服务"，前端页面设计需同时考虑：
- 单份招股书的交互式分析（面向人机协同复核场景）
- 批量新股的报告浏览（面向"批量生成"要求，报告页需支持列表/筛选）
