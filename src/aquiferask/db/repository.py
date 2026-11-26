"""All SQL for documents lives here. Endpoints never write SQL themselves."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import Text, cast, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aquiferask.db.models import Document, Page

FILTER_KEY = re.compile(r"^[a-z_][a-z0-9_]{0,40}$")


def to_dict(doc: Document) -> dict[str, Any]:
    """Same flat shape the API returned on Day 2, so clients don't break."""
    return {
        "id": doc.external_id,
        **doc.metadata_,
        "title": doc.title,
        "doc_type": doc.doc_type,
        "source_url": doc.source_url,
        "licence": doc.licence,
        "published_on": doc.published_on.isoformat() if doc.published_on else None,
    }


def _value_candidates(value: str) -> list[Any]:
    """'10' in a URL may mean the number 10, the text '10', or an item in a list."""
    out: list[Any] = [value, [value]]
    lowered = value.lower()
    if lowered in ("true", "false"):
        out.append(lowered == "true")
    elif re.fullmatch(r"-?\d+", value):
        out.append(int(value))
    elif re.fullmatch(r"-?\d+\.\d+", value):
        out.append(float(value))
    return out


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self, *, q: str | None, filters: dict[str, str], limit: int, offset: int
    ) -> tuple[int, list[dict[str, Any]]]:
        stmt = select(Document)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(Document.title.ilike(like), cast(Document.metadata_, Text).ilike(like))
            )
        for key, value in filters.items():
            stmt = stmt.where(
                or_(*(Document.metadata_.contains({key: v}) for v in _value_candidates(value)))
            )
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self.session.scalars(
            stmt.order_by(Document.external_id).limit(limit).offset(offset)
        )
        return total or 0, [to_dict(d) for d in rows]

    async def get(self, external_id: str) -> dict[str, Any] | None:
        doc = await self.session.scalar(select(Document).where(Document.external_id == external_id))
        return to_dict(doc) if doc else None

    async def search_pages(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Find relevant document pages using PostgreSQL full-text search."""
        terms = re.findall(r"[^\W_]+", query, flags=re.UNICODE)[:20]
        if not terms:
            return []

        tsquery = func.to_tsquery("simple", " | ".join(terms))
        vector = func.to_tsvector("simple", Page.text)
        score = func.ts_rank_cd(vector, tsquery)

        stmt = (
            select(
                Document.external_id.label("document_id"),
                Document.title.label("title"),
                Document.source_url.label("source_url"),
                Page.page_no.label("page_no"),
                Page.headings.label("headings"),
                Page.text.label("text"),
                score.label("score"),
            )
            .join(Page, Page.document_id == Document.id)
            .where(vector.op("@@")(tsquery))
            .order_by(desc(score), Document.title, Page.page_no)
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return [dict(row) for row in result.mappings().all()]
