from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceRef(BaseModel):
    page_number: int = Field(ge=1, description="招股书原始页码")
    paragraph_index: int | None = Field(default=None, ge=0, description="段落索引")
    section_title: str | None = Field(default=None, description="章节标题")
    text_excerpt: str = Field(min_length=1, description="原文引用片段")
    confidence: float = Field(ge=0.0, le=1.0, default=1.0, description="置信度，<0.5标记为低置信度")

    @property
    def is_low_confidence(self) -> bool:
        return self.confidence < 0.5