"""分析服务配置。"""

from __future__ import annotations

import os
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
IPOI_ROOT = PKG_ROOT.parent.parent

RUNTIME_DIR = PKG_ROOT / ".runtime"
ANALYSES_DIR = RUNTIME_DIR / "analyses"
LOGS_DIR = PKG_ROOT / "logs"

# 同机读解析任务 meta
PARSE_TASKS_DIR = Path(
    os.getenv(
        "PARSE_TASKS_DIR",
        str(IPOI_ROOT / "pdf_parsing" / ".runtime" / "tasks"),
    )
)
RETRIEVAL_RUNTIME = Path(
    os.getenv(
        "RETRIEVAL_RUNTIME",
        str(IPOI_ROOT / "retrieval" / ".runtime"),
    )
)
RETRIEVAL_BASE_URL = os.getenv("RETRIEVAL_BASE_URL", "http://127.0.0.1:9101")

HOST = os.getenv("ANALYSIS_HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", os.getenv("ANALYSIS_PORT", "9102")))
SERVICE_VERSION = "0.1.0"

# 分析默认：财务/法务均走 ReAct；可通过环境变量强制规则兜底（冒烟）
FINANCE_RULES_ONLY = os.getenv("ANALYSIS_FINANCE_RULES_ONLY", "0").strip() in (
    "1",
    "true",
    "True",
)
LEGAL_RULES_ONLY = os.getenv("ANALYSIS_LEGAL_RULES_ONLY", "0").strip() in (
    "1",
    "true",
    "True",
)
DEBATE_DIR = Path(
    os.getenv(
        "ANALYSIS_DEBATE_DIR",
        str(PKG_ROOT / ".runtime" / "debate"),
    )
)
