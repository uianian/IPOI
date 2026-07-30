from __future__ import annotations

from pydantic import BaseModel, Field


class ProspectusDocument(BaseModel):
    doc_id: str = Field(description="招股书唯一标识")
    company_name: str = Field(description="公司名称")
    stock_code: str | None = Field(default=None, description="股票代码")
    listing_date: str | None = Field(default=None, description="上市日期")
    file_path: str = Field(description="PDF文件路径")
    total_pages: int = Field(ge=1, description="总页数")
    industry: str | None = Field(default=None, description="所属行业")
    is_profitable: bool | None = Field(default=None, description="是否盈利")


class DocumentChunk(BaseModel):
    chunk_id: str = Field(description="分片唯一标识")
    doc_id: str = Field(description="所属招股书ID")
    page_number: int = Field(ge=1, description="原始页码")
    paragraph_index: int | None = Field(default=None, ge=0, description="段落索引")
    section_title: str | None = Field(default=None, description="章节标题")
    content: str = Field(min_length=1, description="分片文本内容")
    token_count: int = Field(ge=1, description="分片token数量")
    chunk_type: str = Field(default="text", description="分片类型: text/table/chart")
    metadata: dict = Field(default_factory=dict, description="扩展元数据")