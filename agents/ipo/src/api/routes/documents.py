from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.app_state import database, document_index_store
from src.db.repositories.pdf_repo import PdfDocumentRepo
from src.models.api import APIResponse, DocumentIndexRequest, DocumentIndexResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


@router.post("/index", response_model=APIResponse[DocumentIndexResult])
async def index_document(request: DocumentIndexRequest):
    parse_path = Path(request.parse_json_path)
    if not parse_path.is_file():
        raise HTTPException(status_code=400, detail=f"parse_json_path not found: {parse_path}")

    abs_path = str(parse_path.resolve())
    repo = PdfDocumentRepo(database)

    existing = None
    try:
        existing = await repo.get_by_parse_path(abs_path)
    except Exception as e:
        logger.warning("pdf_documents lookup failed (DB may be down): %s", e)

    # Prefer existing registry / on-disk mapping
    doc_id = None
    if existing:
        doc_id = existing.doc_id
    else:
        doc_id = document_index_store.resolve_by_parse_path(abs_path)

    if doc_id is None:
        doc_id = str(uuid.uuid4())

    try:
        result = await document_index_store.build_from_parse(
            doc_id=doc_id,
            parse_json_path=abs_path,
            company_name=request.company_name,
            stock_code=request.stock_code,
            listing_date=request.listing_date,
            force=request.force,
        )
    except Exception as e:
        logger.exception("index build failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    try:
        await repo.upsert(
            doc_id=result.doc_id,
            doc_name=result.doc_name,
            company_name=request.company_name,
            stock_code=request.stock_code,
            listing_date=request.listing_date,
            parse_json_path=abs_path,
            index_path=result.index_path,
            total_pages=result.total_pages,
            chunk_count=result.chunk_count,
        )
    except Exception as e:
        logger.warning("Failed to persist pdf_documents registry: %s", e)

    payload = DocumentIndexResult(
        doc_id=result.doc_id,
        doc_name=result.doc_name,
        reused=result.reused,
        chunk_count=result.chunk_count,
        total_pages=result.total_pages,
        index_path=result.index_path,
        embedding_source=result.embedding_source,
        embedding_model=result.embedding_model,
        skipped_footer=result.skipped_footer,
        skipped_empty_figure=result.skipped_empty_figure,
        company_name=request.company_name,
        stock_code=request.stock_code,
        listing_date=request.listing_date,
    )
    return APIResponse(success=True, data=payload)
