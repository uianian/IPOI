from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    doc_id: str
    file_path: str
    company_name: str
    stock_code: str
    industry: str
    sub_tasks: list[dict[str, Any]]
    legal_result: dict[str, Any]
    finance_result: dict[str, Any]
    sentiment_result: dict[str, Any]
    conflicts: list[dict[str, Any]]
    debate_results: list[dict[str, Any]]
    fused_result: dict[str, Any]
    final_report: dict[str, Any]
    trace_log: list[dict[str, Any]]
    error_message: str