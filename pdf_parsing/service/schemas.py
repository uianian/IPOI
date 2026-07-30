"""与 dataset/interfaces.md 对齐的响应模型。"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class APIError(BaseModel):
    code: str
    message: str


class APIResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[APIError] = None


class ParseStats(BaseModel):
    totalPages: int
    parsedPages: int
    chartCount: int
    tableCount: int
    textChunkCount: int


class StartData(BaseModel):
    taskId: str
    status: Literal["parsing"] = "parsing"
    cached: bool = False
    queuePosition: int = 0
    estimatedSeconds: Optional[int] = None
    sampleKey: Optional[str] = None


class ProgressData(BaseModel):
    progress: int
    stage: Literal["PARSING", "READY", "FAILED"]
    stageDetail: Optional[str] = None
    pagesDone: Optional[int] = None
    pagesTotal: Optional[int] = None
    etaSeconds: Optional[int] = None
    updatedAt: Optional[str] = None
    error: Optional[APIError] = None


class ParseResultData(BaseModel):
    taskId: str
    projectId: str
    mode: Literal["expert"] = "expert"
    status: Literal["completed", "failed"]
    stats: ParseStats
    markdown: str
    parseSummary: Dict[str, Any] = Field(default_factory=dict)
    timing: Optional[Dict[str, Any]] = None
    completedAt: Optional[str] = None
    error: Optional[APIError] = None


class HealthData(BaseModel):
    status: Literal["healthy", "degraded", "down"]
    version: str
    uptime: int
    stubMode: bool
    sampleCount: int
    model: str = "Infinity-Parser2-Flash"
    parseDefaults: Dict[str, Any] = Field(default_factory=dict)
