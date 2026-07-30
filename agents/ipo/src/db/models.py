from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, Boolean
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class ProspectusDocumentORM(Base):
    __tablename__ = "prospectus_documents"

    doc_id = Column(String(64), primary_key=True)
    company_name = Column(String(256), nullable=False)
    stock_code = Column(String(32), nullable=True)
    listing_date = Column(String(32), nullable=True)
    file_path = Column(Text, nullable=False)
    total_pages = Column(Integer, nullable=False)
    industry = Column(String(128), nullable=True)
    is_profitable = Column(Boolean, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


class TraceRecordORM(Base):
    __tablename__ = "trace_records"

    trace_id = Column(String(64), primary_key=True)
    parent_trace_id = Column(String(64), nullable=True, index=True)
    doc_id = Column(String(64), nullable=False, index=True)
    agent_role = Column(String(32), nullable=False, index=True)
    skill_name = Column(String(128), nullable=True)
    step_type = Column(String(32), nullable=False)
    input_summary = Column(Text, nullable=True)
    output_summary = Column(Text, nullable=True)
    evidence_refs = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.now, index=True)
    duration_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)


class SkillRegistrationORM(Base):
    __tablename__ = "skill_registrations"

    skill_name = Column(String(128), primary_key=True)
    version = Column(String(32), primary_key=True)
    description = Column(Text, nullable=True)
    input_schema = Column(Text, nullable=True)
    output_schema = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    registered_at = Column(DateTime, default=datetime.now)


class AnalysisTaskORM(Base):
    __tablename__ = "analysis_tasks"

    task_id = Column(String(64), primary_key=True)
    doc_id = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    progress = Column(Float, default=0.0)
    error_message = Column(Text, nullable=True)


class RiskReportORM(Base):
    __tablename__ = "risk_reports"

    report_id = Column(String(64), primary_key=True)
    doc_id = Column(String(64), nullable=False, index=True)
    company_name = Column(String(256), nullable=False)
    overall_score = Column(Float, nullable=True)
    overall_level = Column(String(32), nullable=True)
    report_data = Column(Text, nullable=True)
    generated_at = Column(DateTime, default=datetime.now)
    trace_root_id = Column(String(64), nullable=True)


class PdfDocumentORM(Base):
    """Lightweight registry: doc_id ↔ full_parse.json + FAISS index path."""

    __tablename__ = "pdf_documents"

    doc_id = Column(String(36), primary_key=True)
    doc_name = Column(String(256), nullable=False, index=True)
    company_name = Column(String(256), nullable=False)
    stock_code = Column(String(32), nullable=True, index=True)
    listing_date = Column(String(32), nullable=True)
    parse_json_path = Column(Text, nullable=False, unique=True)
    index_path = Column(Text, nullable=True)
    total_pages = Column(Integer, nullable=True)
    chunk_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.now)