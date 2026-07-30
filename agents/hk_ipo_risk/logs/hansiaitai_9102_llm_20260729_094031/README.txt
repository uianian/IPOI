翰思艾泰 — 9102 正式 LLM 分析日志目录
================================

样本: task_expert_20260728_000008 / 翰思艾泰 (issuerType=biotech)
analysisId: analysis_20260729_000012
模型: google/gemma-4-31b-it（非 :free）
结果: overallScore=61 HIGH；财务 ReAct react+rules_floor（5 轮）；法务规则流水线

文件说明:
- input.json           启动请求与解析 meta
- start_response.json  start 接口响应
- stream.sse           SSE 实时流完整落盘
- result.json          analysis/result 完整输出（含 thoughts + agents 报告/日志）
- run.log              轮询过程
- artifacts/           服务端 .runtime/analyses/{id} 拷贝
  - report.md          markdown 报告
  - merged.json        finance‖legal 结构化合并
  - logs/*_finance_*.log/.jsonl  财务推理日志
  - logs/legal_*.log   法务步骤日志
- service_relevant.log 服务端相关行

同日另有一次 :free 模型 429 回退后的规则跑:
  ../hansiaitai_9102_20260729_093627/  (score=50 MEDIUM, scoring_mode=rules)
