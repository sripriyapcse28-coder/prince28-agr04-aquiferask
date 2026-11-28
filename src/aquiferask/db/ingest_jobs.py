"""Database operations for ingestion jobs and their individual items."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aquiferask.db.models import Document, IngestItem, IngestJob, ParseFailure
from aquiferask.ingest.store import document_id

OPEN = ("queued", "running")


class IngestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def known_ids(self) -> set[str]:
        document_ids = await self.session.scalars(
            select(Document.external_id).where(Document.doc_type != "record")
        )
        failed_hashes = await self.session.scalars(select(ParseFailure.sha256))

        return set(document_ids) | {document_id(value) for value in failed_hashes}

    async def create(self, records: list[dict]) -> tuple[str, list[int]]:
        job = IngestJob(
            id=uuid4().hex,
            requested=len(records),
            items=[IngestItem(record=record) for record in records],
        )
        self.session.add(job)
        await self.session.commit()

        return job.id, [item.id for item in job.items]

    async def progress(self, job_id: str) -> dict | None:
        job = await self.session.get(IngestJob, job_id)
        if job is None:
            return None

        statement = (
            select(
                IngestItem.status,
                func.count(IngestItem.id),
                func.coalesce(func.sum(IngestItem.pages), 0),
                func.max(IngestItem.updated_at),
            )
            .where(IngestItem.job_id == job_id)
            .group_by(IngestItem.status)
        )
        rows = (await self.session.execute(statement)).all()

        counts = {
            "queued": 0,
            "running": 0,
            "done": 0,
            "skipped": 0,
            "failed": 0,
        }
        pages = 0
        latest = job.created_at

        for status, count, page_count, updated_at in rows:
            counts[status] = count
            pages += page_count
            if updated_at and (latest is None or updated_at > latest):
                latest = updated_at

        finished = counts["queued"] + counts["running"] == 0
        now = latest if finished else datetime.now(UTC)
        seconds = (now - job.created_at).total_seconds() if job.created_at else 0

        status = "finished" if finished else "running" if counts["running"] else "queued"

        return {
            "job_id": job.id,
            "status": status,
            "requested": job.requested,
            "counts": counts,
            "pages": pages,
            "seconds": round(seconds, 1),
            "created_at": job.created_at,
            "dead_letter": await self.dead_letter(job_id=job_id),
        }

    async def dead_letter(self, job_id: str | None = None, limit: int = 50) -> list[dict]:
        statement = (
            select(IngestItem)
            .where(IngestItem.status == "failed")
            .order_by(IngestItem.updated_at.desc())
            .limit(limit)
        )

        if job_id:
            statement = statement.where(IngestItem.job_id == job_id)

        items = (await self.session.scalars(statement)).all()

        return [
            {
                "item_id": item.id,
                "job_id": item.job_id,
                "url": item.record.get("url", ""),
                "path": item.record.get("path", ""),
                "attempts": item.attempts,
                "error": item.error,
            }
            for item in items
        ]

    async def failed_records(self) -> list[dict]:
        items = await self.session.scalars(
            select(IngestItem)
            .where(IngestItem.status == "failed")
            .order_by(IngestItem.updated_at.desc())
        )

        records = {}
        for item in items:
            url = item.record.get("url", "")
            records.setdefault(url, item.record)

        return list(records.values())

    async def open_item_ids(self) -> list[int]:
        statement = select(IngestItem.id).where(IngestItem.status.in_(OPEN)).order_by(IngestItem.id)
        return list(await self.session.scalars(statement))
