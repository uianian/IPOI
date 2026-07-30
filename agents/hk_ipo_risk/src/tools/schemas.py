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
        "章节化召回非主表证据。",
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
