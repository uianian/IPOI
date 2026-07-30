"""检索前置内部服务配置。force / agents / topK 仅后端调参。"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = ROOT / ".runtime"
PREPS_DIR = RUNTIME_DIR / "preps"
INDEX_ROOT = RUNTIME_DIR / "indexes"

HOST = os.getenv("RETRIEVAL_HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", os.getenv("RETRIEVAL_PORT", "9101")))
SERVICE_VERSION = "0.1.0"

FORCE_REBUILD = os.getenv("RETRIEVAL_FORCE", "0").strip() in ("1", "true", "True")
PREPARE_AGENTS = [
    a.strip()
    for a in os.getenv("RETRIEVAL_PREPARE_AGENTS", "finance,legal").split(",")
    if a.strip()
]
PACKAGE_TOP_K = int(os.getenv("RETRIEVAL_PACKAGE_TOP_K", "5"))
