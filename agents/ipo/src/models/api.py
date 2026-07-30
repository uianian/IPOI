from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from src.models.enums import ExecutionStatus

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    success: bool = Field(description="请求是否成功")
    data: T | None = Field(default=None, description="响应数据")
    error: str | None = Field(default=None, description="错误信息")
    trace_id: str | None = Field(default=None, description="追踪ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="响应时间")


class AnalysisRequest(BaseModel):
    doc_id: str | None = Field(default=None, description="招股书ID（已有文档时）")
    file_path: str | None = Field(default=None, description="招股书PDF路径（新上传时）")
    company_name: str | None = Field(default=None, description="公司名称")
    stock_code: str | None = Field(default=None, description="股票代码")
    options: dict = Field(default_factory=dict, description="分析选项")


class AnalysisTask(BaseModel):
    task_id: str = Field(description="任务ID")
    doc_id: str = Field(description="招股书ID")
    status: ExecutionStatus = Field(default=ExecutionStatus.PENDING, description="任务状态")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="进度")
    error_message: str | None = Field(default=None, description="错误信息")


class AnalysisStatus(BaseModel):
    task_id: str = Field(description="任务ID")
    status: ExecutionStatus = Field(description="任务状态")
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="进度")
    current_step: str | None = Field(default=None, description="当前步骤")
    completed_agents: list[str] = Field(default_factory=list, description="已完成的Agent")
    pending_agents: list[str] = Field(default_factory=list, description="待执行的Agent")


class HealthStatus(BaseModel):
    status: str = Field(default="ok", description="系统状态")
    agents: dict[str, bool] = Field(default_factory=dict, description="各Agent健康状态")
    skills: dict[str, bool] = Field(default_factory=dict, description="各Skill健康状态")
    llm_available: bool = Field(default=False, description="LLM服务是否可用")
    database_available: bool = Field(default=False, description="数据库是否可用")


class DocumentIndexRequest(BaseModel):
    company_name: str = Field(description="公司名称")
    stock_code: str = Field(description="股票代码")
    listing_date: str = Field(description="上市日期 YYYY-MM-DD")
    parse_json_path: str = Field(description="full_parse.json 路径")
    force: bool = Field(default=False, description="强制重建索引")


class DocumentIndexResult(BaseModel):
    doc_id: str
    doc_name: str
    reused: bool
    chunk_count: int
    total_pages: int
    index_path: str
    embedding_source: str | None = None
    embedding_model: str | None = None
    skipped_footer: int = 0
    skipped_empty_figure: int = 0
    company_name: str | None = None
    stock_code: str | None = None
    listing_date: str | None = None