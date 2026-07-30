from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from src.db.database import Database
from src.db.models import PdfDocumentORM


class PdfDocumentRepo:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def get_by_id(self, doc_id: str) -> PdfDocumentORM | None:
        async with self._db.session() as session:
            result = await session.execute(
                select(PdfDocumentORM).where(PdfDocumentORM.doc_id == doc_id)
            )
            return result.scalar_one_or_none()

    async def get_by_parse_path(self, parse_json_path: str) -> PdfDocumentORM | None:
        abs_path = str(Path(parse_json_path).resolve())
        async with self._db.session() as session:
            result = await session.execute(
                select(PdfDocumentORM).where(PdfDocumentORM.parse_json_path == abs_path)
            )
            return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        doc_id: str,
        doc_name: str,
        company_name: str,
        stock_code: str | None,
        listing_date: str | None,
        parse_json_path: str,
        index_path: str | None,
        total_pages: int | None = None,
        chunk_count: int | None = None,
    ) -> PdfDocumentORM:
        abs_path = str(Path(parse_json_path).resolve())
        async with self._db.session() as session:
            result = await session.execute(
                select(PdfDocumentORM).where(PdfDocumentORM.parse_json_path == abs_path)
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.company_name = company_name
                existing.stock_code = stock_code
                existing.listing_date = listing_date
                existing.doc_name = doc_name
                existing.index_path = index_path
                if total_pages is not None:
                    existing.total_pages = total_pages
                if chunk_count is not None:
                    existing.chunk_count = chunk_count
                await session.commit()
                await session.refresh(existing)
                return existing

            orm = PdfDocumentORM(
                doc_id=doc_id,
                doc_name=doc_name,
                company_name=company_name,
                stock_code=stock_code,
                listing_date=listing_date,
                parse_json_path=abs_path,
                index_path=index_path,
                total_pages=total_pages,
                chunk_count=chunk_count,
                created_at=datetime.now(),
            )
            session.add(orm)
            await session.commit()
            await session.refresh(orm)
            return orm
