from __future__ import annotations

from typing import Any, Awaitable, Callable

ToolHandler = Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]


def _fn(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


FINANCE_TOOL_SCHEMAS: list[dict[str, Any]] = [
    _fn(
        "retrieve_finance",
        "检索三张财务主表。",
        {
            "reason": {"type": "string", "description": "为何需要检索"},
        },
    ),
    _fn(
        "extract_metrics",
        "从主表抽取标准指标。",
        {
            "reason": {"type": "string"},
        },
    ),
    _fn(
        "derive_gates",
        "计算盈利/现金跑道/biotech门控。",
        {
            "reason": {"type": "string"},
        },
    ),
    _fn(
        "calc_cash_runway",
        "未盈利时测算现金跑道。",
        {
            "reason": {"type": "string"},
        },
    ),
    _fn(
        "retrieve_context_evidence",
        "章节化召回非主表证据（兼容旧路径；优先用 run_finance_skill）。",
        {
            "intent": {
                "type": "string",
                "enum": ["business_context", "business_model", "franchise", "supply_chain", "financing_dependency", "concentration"],
            },
            "query": {"type": "string"},
            "section_hint": {
                "type": "string",
            },
            "top_k": {"type": "integer", "description": "返回条数，默认5"},
            "prefer_source_type": {
                "type": "string",
                "enum": ["text", "table", "mixed"],
            },
            "reason": {"type": "string"},
        },
        required=["intent", "query"],
    ),
    _fn(
        "run_finance_skill",
        "执行一个专项财务审查 skill：规则指标打包或章节检索+LLM 抽取。",
        {
            "skill_name": {
                "type": "string",
                "enum": [
                    "finance_profitability",
                    "finance_cash_flow",
                    "finance_solvency",
                    "finance_business_context",
                ],
            },
            "focus_hint": {"type": "string", "description": "可选：本次审查侧重点"},
            "reason": {"type": "string"},
        },
        required=["skill_name"],
    ),
    _fn(
        "search_finance_evidence",
        "按 query 到指定章节补充召回带页码的财务/业务证据。",
        {
            "query": {
                "type": "string",
                "description": "繁體中文检索词，空格分隔",
            },
            "intent": {
                "type": "string",
                "enum": [
                    "business_context",
                    "business_model",
                    "franchise",
                    "supply_chain",
                    "financing_dependency",
                    "concentration",
                ],
            },
            "section_hint": {"type": "string"},
            "top_k": {"type": "integer", "description": "返回条数，默认6"},
            "reason": {"type": "string"},
        },
        required=["query", "intent"],
    ),
    _fn(
        "run_finance_rule_checks",
        "运行财务规则引擎交叉核对，返回规则命中与覆盖缺口。submit 前建议调用。",
        {
            "reason": {"type": "string"},
        },
    ),
    _fn(
        "submit_finance_report",
        "提交最终 JSON 并结束。",
        {
            "risk_score": {"type": "number", "description": "0-100，越高风险越大"},
            "risk_level": {
                "type": "string",
                "enum": ["very_low", "low", "medium", "high", "very_high"],
            },
            "dimensions": {
                "type": "array",
                "description": "四维分析",
                "items": {
                    "type": "object",
                    "properties": {
                        "dimension": {"type": "string"},
                        "analysis": {"type": "string"},
                    },
                },
            },
            "score_breakdown": {
                "type": "array",
                "description": "可解释扣分项",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "delta": {"type": "number"},
                        "rule_ref": {"type": "string"},
                        "metric_value": {"type": "string"},
                        "note": {"type": "string"},
                        "evidence_page": {"type": "integer"},
                    },
                },
            },
            "risk_points": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "level": {"type": "string"},
                        "rule_ref": {"type": "string"},
                        "description": {"type": "string"},
                        "metric_value": {"type": "string"},
                        "evidence_page": {"type": "integer"},
                    },
                },
            },
            "negative_findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "rule_ref": {"type": "string"},
                        "description": {"type": "string"},
                    },
                },
            },
            "reasoning": {"type": "string", "description": "简短中文推理链"},
            "summary": {"type": "string", "description": "一句话中文摘要"},
        },
        required=["risk_score", "risk_level", "reasoning", "summary"],
    ),
]


LEGAL_TOOL_SCHEMAS: list[dict[str, Any]] = [
    _fn(
        "retrieve_legal",
        "初始化法务证据包（检索包+全书grep基线）。第一步必调。",
        {
            "reason": {"type": "string", "description": "为何需要检索"},
        },
    ),
    _fn(
        "run_legal_skill",
        "执行一个专项合规审查 skill：定向检索→LLM结构化抽取→阈值判定→置信度。",
        {
            "skill_name": {
                "type": "string",
                "enum": [
                    "legal_governance",
                    "legal_shareholder_rights",
                    "legal_related_party",
                    "legal_contracts_and_ip",
                    "legal_regulatory_litigation",
                ],
            },
            "focus_hint": {"type": "string", "description": "可选：本次审查侧重点"},
            "reason": {"type": "string"},
        },
        required=["skill_name"],
    ),
    _fn(
        "search_legal_evidence",
        "按 query 到指定章节补充召回带页码的原文证据（证据不足/反思时用）。",
        {
            "query": {
                "type": "string",
                "description": "繁體中文检索词（招股书为繁体），空格分隔多个词",
            },
            "intent": {
                "type": "string",
                "enum": [
                    "redemption",
                    "related_party",
                    "concentration",
                    "regulatory",
                    "litigation",
                    "ip",
                    "financing_dependency",
                    "business_context",
                ],
            },
            "section_hint": {"type": "string"},
            "top_k": {"type": "integer", "description": "返回条数，默认6"},
            "reason": {"type": "string"},
        },
        required=["query", "intent"],
    ),
    _fn(
        "run_rule_checks",
        "运行规则引擎（doc§3.1/3.2/3.3/3.5）交叉核对，返回规则命中与覆盖缺口。submit 前必调。",
        {
            "reason": {"type": "string"},
        },
    ),
    _fn(
        "submit_legal_report",
        "提交法务终裁报告并结束。必须写非空 summary+reasoning；risk_points 可空（系统从 skill 填充）。",
        {
            "risk_points": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "level": {"type": "string", "enum": ["high", "medium", "low"]},
                        "description": {"type": "string"},
                        "legal_basis": {"type": "string"},
                        "metric_value": {"type": "string"},
                        "evidence_page": {"type": "integer"},
                        "evidence_excerpt": {"type": "string"},
                        "skill": {"type": "string"},
                    },
                },
            },
            "negative_findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "description": {"type": "string"},
                    },
                },
            },
            "reasoning": {
                "type": "string",
                "description": "必填：2-5句繁體中文风险归因与终裁说明，禁止空字符串",
            },
            "summary": {
                "type": "string",
                "description": "必填：一句繁體中文终裁摘要，禁止空字符串",
            },
        },
        required=["reasoning", "summary"],
    ),
]


MARKET_TOOL_SCHEMAS: list[dict[str, Any]] = [
    _fn("lookup_market_row", "按股票代码读取上市前市场宽表及数据边界。", {}),
    _fn(
        "run_market_skill",
        "分析一个市场维度。",
        {"skill": {"type": "string", "enum": ["market_macro", "market_industry", "market_ipo_heat", "market_sentiment_news"]}},
        required=["skill"],
    ),
    _fn("search_market_evidence", "检查本地舆情，缺失时按配置使用Firecrawl。", {}),
    _fn("run_market_rule_checks", "运行确定性阈值与历史同期校准，产生rules floor。", {}),
    _fn(
        "score_market_with_llm",
        "提交独立LLM风险评分，必须引用证据ID。",
        {
            "risk_score": {"type": "number", "minimum": 0, "maximum": 100},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "score_reason": {"type": "string"},
            "evidence_ids": {"type": "array", "items": {"type": "string"}},
            "dimension_scores": {"type": "object"},
        },
        required=["risk_score", "confidence", "score_reason", "evidence_ids"],
    ),
    _fn(
        "submit_market_report",
        "唯一结束动作，合并LLM分与rules floor并生成报告。",
        {
            "summary": {"type": "string"},
            "module_assessments": {"type": "object"},
            "risk_points": {"type": "array", "items": {"type": "object"}},
        },
        required=["summary"],
    ),
]


class ToolRegistry:
    """名称 → OpenAI tool schema + async handler(args, state)->result。"""

    def __init__(self) -> None:
        self._schemas: dict[str, dict[str, Any]] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, schema: dict[str, Any], handler: ToolHandler) -> None:
        name = schema["function"]["name"]
        self._schemas[name] = schema
        self._handlers[name] = handler

    def openai_tools(self, names: list[str] | None = None) -> list[dict[str, Any]]:
        if names is None:
            return list(self._schemas.values())
        return [self._schemas[n] for n in names if n in self._schemas]

    def names(self) -> list[str]:
        return list(self._schemas.keys())

    async def execute(self, name: str, arguments: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        if name not in self._handlers:
            return {"ok": False, "error": f"unknown tool: {name}"}
        try:
            return await self._handlers[name](arguments or {}, state)
        except Exception as e:
            return {"ok": False, "error": str(e), "tool": name}
