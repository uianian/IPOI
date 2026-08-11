from __future__ import annotations

"""总控辩论素材包：法务（未来含财务/市场）Agent 的证据+推理+结论持久化。

总控决策 Agent 与三个专家 Agent 辩论时：
1. 直接引用 dossier 的 claims 做陈述（statement + evidence_refs 页码/切片）；
2. 证据不充分时，按 retrieval_queries 记录的检索方式增量调用
   `search_legal_evidence`（见 src/skills/legal_toolbox.py）继续找证据。
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.models.evidence import EvidenceRef


class DebateClaim(BaseModel):
    """一条可辩论主张：结论 + 证据 + 推理 + 补证据入口。"""

    claim_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent: str = "legal"
    skill: str | None = None
    code: str = ""
    level: str = "medium"  # high / medium / low
    confidence: str = "low"  # doc§5.2: high / medium / low
    statement: str = ""
    legal_basis: str | None = None
    metric_value: Any = None
    reasoning: str = ""
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    # 该主张相关的补证据检索方式（intent/query），辩论时可增量复用
    retrieval_queries: list[dict[str, Any]] = Field(default_factory=list)


class DebateDossier(BaseModel):
    """一次 Agent 分析的完整辩论素材包。"""

    dossier_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent: str = "legal"
    doc_id: str = ""
    doc_name: str | None = None
    issuer_type: str = "general"
    # HTTP 关联：client_project_id / task_id / analysis_id；CLI 可空
    client_project_id: str | None = None
    task_id: str | None = None
    analysis_id: str | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    risk_score: float = 0.0
    risk_level: str = "very_low"
    summary: str = ""
    reasoning: str = ""
    claims: list[DebateClaim] = Field(default_factory=list)
    negative_findings: list[dict[str, Any]] = Field(default_factory=list)
    rule_flags: dict[str, Any] = Field(default_factory=dict)
    # 全程检索记录：辩论阶段补证据时的起点
    retrieval_queries: list[dict[str, Any]] = Field(default_factory=list)
    run_log: dict[str, Any] = Field(default_factory=dict)


def save_dossier(dossier: DebateDossier, out_dir: Path | str) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out / f"{dossier.doc_id or 'doc'}_{dossier.agent}_dossier_{ts}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(dossier.model_dump(), f, ensure_ascii=False, indent=2, default=str)
    return path


def load_dossier(path: Path | str) -> DebateDossier:
    with Path(path).open(encoding="utf-8") as f:
        return DebateDossier(**json.load(f))
