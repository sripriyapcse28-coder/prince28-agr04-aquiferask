"""ARQ worker functions for downloading, parsing, and extracting documents."""

import asyncio
import hashlib
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from arq import Retry
from sqlalchemy import select

from aquiferask.db.models import Document, IngestItem
from aquiferask.ingest.fetch import HostGate, Robots, make_client
from aquiferask.ingest.parse import ParseError, parse_file
from aquiferask.ingest.store import document_id, save_document, save_failure
from aquiferask.llm.extract import document_text, extract, save
from aquiferask.llm.gateway import LLMUnavailable


class Permanent(Exception):
    """An error that will not succeed if the worker retries it."""


class Pace:
    """Spread external calls evenly across the configured requests per minute."""

    def __init__(
        self,
        per_minute: int,
        *,
        clock=time.monotonic,
        sleep=asyncio.sleep,
    ) -> None:
        if per_minute < 1:
            raise ValueError("per_minute must be at least 1")

        self.interval = 60.0 / per_minute
        self.clock = clock
        self.sleep = sleep
        self.next_call = 0.0
        self.lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self.lock:
            now = self.clock()
            delay = max(0.0, self.next_call - now)

            if delay:
                await self.sleep(delay)

            self.next_call = max(now, self.next_call) + self.interval


def sha256_of(path: Path) -> str:
    """Calculate a file's SHA-256 without loading the whole file into memory."""
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def raw_url(record: dict) -> str:
    """Convert a GitHub blob URL into a raw URL pinned to its commit."""
    if record.get("via") != "git":
        return record["url"]

    parts = urlsplit(record["url"])
    segments = parts.path.strip("/").split("/")

    if parts.netloc != "github.com" or len(segments) < 5 or segments[2] != "blob":
        return record["url"]

    commit = record.get("commit")
    if not commit:
        raise Permanent("Git record is missing its commit")

    file_path = "/".join(segments[4:])
    return f"https://raw.githubusercontent.com/{segments[0]}/{segments[1]}/{commit}/{file_path}"


async def get_file(
    record: dict,
    folder: Path,
    client: httpx.AsyncClient | None = None,
    sleep=asyncio.sleep,
) -> Path:
    """Return an existing local file or download the source into a temporary folder."""
    local_path = Path(record["path"])

    if local_path.is_file():
        return local_path

    if record.get("via") == "manual":
        raise Permanent(f"File was added by hand and is missing: {local_path}")

    url = raw_url(record)
    own_client = client is None
    client = client or make_client(2)

    try:
        robots = Robots(client)
        allowed, crawl_delay = await robots.check(url)

        if not allowed:
            raise Permanent(f"Blocked by robots.txt: {url}")

        gate = HostGate(0.5, sleep)
        await gate.wait(urlsplit(url).netloc, crawl_delay)

        try:
            response = await client.get(url)
        except httpx.HTTPError as error:
            raise RuntimeError(f"Download failed: {type(error).__name__}") from error

        if response.status_code == 404:
            raise Permanent(f"HTTP 404: {url}")

        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}: {url}")

        folder.mkdir(parents=True, exist_ok=True)
        filename = Path(urlsplit(url).path).name or "download"
        target = folder / filename
        target.write_bytes(response.content)

        if target.suffix.lower() == ".pdf" and b"%PDF-" not in response.content[:1024]:
            raise Permanent("Downloaded response is not a valid PDF")

        return target

    finally:
        if own_client:
            await client.aclose()


def plan(
    records: list[dict],
    known: set[str],
    *,
    source: str = "",
    limit: int = 0,
) -> list[dict]:
    """Select downloaded, new records without changing the caller's known set."""
    seen = set(known)
    selected = []

    for record in records:
        if record.get("status") != "downloaded":
            continue

        if source and record.get("source") != source:
            continue

        digest = record.get("sha256")

        if not digest:
            continue

        doc_id = document_id(digest)

        if doc_id in seen:
            continue

        seen.add(doc_id)
        selected.append(record)

        if limit > 0 and len(selected) >= limit:
            break

    return selected


async def process(ctx: dict, item: IngestItem) -> tuple[str, int]:
    """Process one item without holding a database connection during slow work."""
    record = dict(item.record)
    sessionmaker = ctx["sessionmaker"]

    with tempfile.TemporaryDirectory() as folder:
        path = await get_file(record, Path(folder), ctx["http"])
        record["sha256"] = await asyncio.to_thread(sha256_of, path)
        doc_id = document_id(record["sha256"])

        # Check the database, then close the session before lengthy PDF parsing.
        async with sessionmaker() as session:
            document = await session.scalar(select(Document).where(Document.external_id == doc_id))

            if document is not None:
                title = document.title
                metadata = dict(document.metadata_ or {})
            else:
                title = ""
                metadata = {}

        status = "skipped"

        if not metadata:
            try:
                parsed = await asyncio.to_thread(parse_file, path)
            except ParseError as error:
                async with sessionmaker() as session:
                    await save_failure(session, record, error)

                raise Permanent(f"parse: {error.reason}") from error

            async with sessionmaker() as session:
                await save_document(session, record, parsed)
                document = await session.scalar(
                    select(Document).where(Document.external_id == doc_id)
                )

                if document is None:
                    raise RuntimeError("Document was not found after saving")

                title = document.title
                metadata = dict(document.metadata_ or {})

            status = "done"

    pages = int(metadata.get("pages", 0))
    task = ctx.get("extract")
    note = metadata.get("extract") or {}

    if task and (note.get("prompt") != task["version"] or "error" in note):
        await ctx["pace"].wait()

        # Read text in a short session and close it before the external LLM call.
        async with sessionmaker() as session:
            document = await session.scalar(select(Document).where(Document.external_id == doc_id))

            if document is None:
                raise RuntimeError("Document disappeared before extraction")

            title = document.title
            text = await document_text(session, document, task["chars"])
            await session.commit()

        if not text.strip():
            raise Permanent("extract: document has no parsed page text")

        result = await extract(
            ctx["gateway"],
            task["schema"],
            task["prompt"],
            task["version"],
            title,
            text,
        )

        async with sessionmaker() as session:
            document = await session.scalar(select(Document).where(Document.external_id == doc_id))

            if document is None:
                raise RuntimeError("Document disappeared before extraction save")

            await save(session, document, result, task["version"])

        if result.record is None:
            errors = result.errors or ["Extraction failed"]
            raise Permanent(f"extract: {errors[-1][:200]}")

        status = "done"

    return status, pages


async def ingest_document(ctx: dict, item_id: int) -> str:
    """ARQ entry point: update item status and process one queued document."""
    sessionmaker = ctx["sessionmaker"]

    # Mark the item running and copy its data before doing slow work.
    async with sessionmaker() as session:
        item = await session.get(IngestItem, item_id)

        if item is None:
            return "ignored"

        # Ignore messages that have already been completed.
        if item.status in {"done", "skipped", "failed"}:
            return "ignored"

        # A worker may have died while this item was running.
        if item.status == "running" and item.attempts >= 3:
            item.status = "failed"
            item.error = "Worker never finished after 3 tries"
            await session.commit()
            return "failed"

        item.status = "running"
        item.attempts += 1
        item.error = ""

        record_item = IngestItem(
            id=item.id,
            job_id=item.job_id,
            record=dict(item.record),
        )

        await session.commit()

    try:
        status, pages = await process(ctx, record_item)

    except Permanent as error:
        async with sessionmaker() as session:
            item = await session.get(IngestItem, item_id)

            if item is not None:
                item.status = "failed"
                item.error = str(error)[:4000]
                await session.commit()

        return "failed"

    except LLMUnavailable as error:
        async with sessionmaker() as session:
            item = await session.get(IngestItem, item_id)

            if item is not None:
                if item.attempts >= 3:
                    item.status = "failed"
                    item.error = f"gave up after 3 tries: {error}"[:4000]
                else:
                    item.status = "queued"
                    item.error = f"{type(error).__name__}: {error}"[:4000]

                await session.commit()

                if item.status == "failed":
                    return "failed"

        raise Retry(defer=5) from error

    except Exception as error:
        # Keep the item eligible for another ARQ attempt.
        async with sessionmaker() as session:
            item = await session.get(IngestItem, item_id)

            if item is not None:
                item.status = "queued"
                item.error = f"{type(error).__name__}: {error}"[:4000]
                await session.commit()

        raise

    async with sessionmaker() as session:
        item = await session.get(IngestItem, item_id)

        if item is not None:
            item.status = status
            item.pages = pages
            item.error = ""
            await session.commit()

    return status
