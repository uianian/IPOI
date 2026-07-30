"""服务配置（固化解析参数；当前以桩模式服务前端）。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = ROOT / ".runtime"
TASKS_DIR = RUNTIME_DIR / "tasks"
CACHE_DIR = RUNTIME_DIR / "cache"
SAMPLES_DIR = ROOT / "output" / "samples_batch"
PDF_DIR = ROOT / "pdf"

HOST = "0.0.0.0"
PORT = 9100  # 机房放行区间 9100–9200；启动脚本可用 PORT= 覆盖
SERVICE_VERSION = "0.1.0"

# 检索前置服务（解析完成后自动 prepare；前端不直连）
RETRIEVAL_BASE_URL = "http://127.0.0.1:9101"
# 分析服务（9100 网关反代 analysis/* → 此地址；前端只认 9100）
ANALYSIS_BASE_URL = "http://127.0.0.1:9102"

# 解析参数固化（真解析启用时使用）
PARSE_DEFAULTS = {
    "gpus": "auto",
    "page_workers": 2,
    "min_free_mib": 20000,
    "dpi": 300,
    "batch_size": 2,
    "max_new_tokens": 16384,
    "rotate_mode": "none",
    "rotate_fallback": False,
    "no_figures": True,
    "save_risk_chunks": True,
    "skip_qa": True,
}

# 当前无空闲 GPU：仅用现有解析结果
STUB_MODE = True
# 桩模式模拟进度总时长（秒），便于前端看到进度条
STUB_PROGRESS_SECONDS = 3.0
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
QUEUE_FULL_LIMIT = 20
