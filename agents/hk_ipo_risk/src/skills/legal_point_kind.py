from __future__ import annotations

"""法务风险点 point_kind 分类：供 Skill 校验与参考分合并共用。

服务端启发式可收紧模型输出，防止样板风险因素抬分。
"""

import re
from typing import Any

POINT_KINDS = frozenset(
    {
        "issuer_specific",
        "structural",
        "boilerplate",
        "disclosure_only",
        "benign_negative",
    }
)

# 套话/行业通用风险因素（无具体发行人事件时）
_BOILERPLATE_RE = re.compile(
    r"(可能|任何調查|任何调查|受[^。]{0,40}約束|受[^。]{0,40}约束|"
    r"虛假索賠|虚假索赔|反回扣|耗費[^。]{0,20}時間|耗费[^。]{0,20}时间|"
    r"產生負面影響|产生负面影响|監管架構變化|监管架构变化|"
    r"競爭者進入|竞争者进入|第三方質疑|第三方质疑)",
    re.IGNORECASE,
)

# 发行人特异事实信号
_SPECIFIC_RE = re.compile(
    r"(\d+(\.\d+)?\s*%|"
    r"人民幣\s*[\d,.]+|人民币\s*[\d,.]+|"
    r"駁回|驳回|"
    r"截至\s*\d{4}|於\s*\d{4}|"
    r"百萬元|亿元|億元|"
    r"終止購回|终止购回|特別權利|特别权利|"
    r"一致行動|一致行动|"
    r"滯納金|滞纳金|補繳|补缴|"
    r"框架協議|框架协议)",
    re.IGNORECASE,
)

_BENIGN_RE = re.compile(
    r"(未涉及|概未牽涉|概未牵涉|無未決|无未决|未面臨任何|未面临任何|"
    r"不存在重大訴訟|不存在重大诉讼|ABSENT)",
    re.IGNORECASE,
)

_STRUCTURAL_CODES = frozenset(
    {
        "GOVERNANCE_CONTROL_GT_50",
        "GOVERNANCE_AB_SHARES",
        "GOVERNANCE_CONCERT_PARTY",
        "GOVERNANCE_BOARD_INDEPENDENCE",
    }
)


def _text_blob(point: dict[str, Any]) -> str:
    parts = [
        str(point.get("description") or ""),
        str(point.get("evidence_excerpt") or ""),
        str(point.get("evidence_note") or ""),
        str(point.get("note") or ""),
    ]
    return " ".join(parts)


def classify_legal_point_kind(point: dict[str, Any]) -> str:
    """返回规范化 point_kind；启发式可收紧（防抬分）。"""
    code = str(point.get("code") or "").upper()
    text = _text_blob(point)
    raw = str(point.get("point_kind") or "").strip().lower()
    model_kind = raw if raw in POINT_KINDS else ""

    if code.endswith("_DISCLOSURE") or (
        "DISCLOSURE" in code and "存在" in text and "披露" in text
    ):
        return "disclosure_only"
    if "ABSENT" in code or (
        _BENIGN_RE.search(text)
        and any(k in text for k in ("訴訟", "诉讼", "仲裁", "行政程序"))
    ):
        return "benign_negative"

    has_specific = bool(_SPECIFIC_RE.search(text))
    has_boiler = bool(_BOILERPLATE_RE.search(text))

    # 套话且无特异事实 → boilerplate（优先于模型的 issuer_specific）
    if has_boiler and not has_specific:
        return "boilerplate"

    if code == "GOVERNANCE_CONTROL_GT_50":
        # 控股>50% 一律 structural（忽略模型 issuer_specific），与设计对齐
        return "structural"
    if code in _STRUCTURAL_CODES:
        # 其他治理结构码：默认 structural；模型标 issuer_specific 且有特异事实时可保留
        if model_kind == "issuer_specific" and has_specific:
            return "issuer_specific"
        return "structural"

    if model_kind == "boilerplate":
        return "boilerplate"
    if model_kind == "benign_negative":
        return "benign_negative"
    if model_kind == "disclosure_only":
        return "disclosure_only"
    if model_kind == "structural":
        return "structural"
    if model_kind == "issuer_specific":
        return "issuer_specific"

    # 无模型 kind：有特异事实 → issuer_specific，否则 structural（偏保守不计套话满额）
    if has_specific:
        return "issuer_specific"
    if has_boiler:
        return "boilerplate"
    return "structural"


def is_disclosure_rule_code(code: str) -> bool:
    return str(code or "").upper().endswith("_DISCLOSURE")
