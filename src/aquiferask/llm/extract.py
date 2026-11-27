"""Extract and store structured metadata from groundwater documents."""

import asyncio
import json
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aquiferask.db.models import Document, Page
from aquiferask.llm.gateway import LLMGateway, LLMUnavailable

RESERVED = {
    "source",
    "path",
    "parser",
    "pages",
    "tables",
    "chars",
    "extract",
}


def parse_json(reply: str) -> dict:
    """Extract a JSON object from an LLM response."""
    start = reply.find("{")
    end = reply.rfind("}")

    if start < 0 or end < start:
        raise ValueError("No JSON object found in response")

    value = json.loads(reply[start : end + 1])

    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")

    return value


def explain(error: Exception) -> str:
    """Make validation errors concise enough to send back to the model."""
    if isinstance(error, ValidationError):
        details = []
        for item in error.errors()[:6]:
            location = ".".join(str(part) for part in item["loc"])
            details.append(f"{location}: {item['msg']}")
        return "; ".join(details)

    return str(error)[:1000]


@dataclass
class Extraction:
    """One document's extraction result and usage information."""

    record: BaseModel | None = None
    attempts: int = 0
    errors: list[str] | None = None
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_inr: float = 0.0


async def extract(
    gateway: LLMGateway,
    schema: type[BaseModel],
    prompt: str,
    version: str,
    title: str,
    text: str,
    *,
    max_attempts: int = 3,
    native_schema: bool = False,
) -> Extraction:
    """Ask the gateway for JSON and validate it against a Pydantic model."""
    json_schema = schema.model_json_schema()

    messages = [
        {
            "role": "system",
            "content": (
                f"{prompt}\n\n"
                "Return JSON matching this schema exactly:\n"
                f"{json.dumps(json_schema, ensure_ascii=False)}"
            ),
        },
        {
            "role": "user",
            "content": f"Title: {title}\n<document>\n{text}\n</document>",
        },
    ]

    errors = []
    result = Extraction(errors=errors)

    options = {"temperature": 0}
    if native_schema:
        options["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "document_metadata",
                "strict": True,
                "schema": json_schema,
            },
        }

    for attempt in range(1, max_attempts + 1):
        response = await gateway.generate(
            messages,
            purpose="extract",
            prompt_version=version,
            **options,
        )

        result.attempts = attempt
        result.model = response.model
        result.tokens_in += response.tokens_in
        result.tokens_out += response.tokens_out
        result.cost_inr += response.cost_inr

        try:
            data = parse_json(response.text)
            result.record = schema.model_validate(data)
            return result

        except (ValueError, ValidationError) as error:
            message = explain(error)
            errors.append(message)

            if attempt < max_attempts:
                messages.extend(
                    [
                        {"role": "assistant", "content": response.text},
                        {
                            "role": "user",
                            "content": (
                                "Your previous response was invalid. "
                                f"Validation error: {message}\n"
                                "Return a corrected JSON object only. "
                                "Follow the supplied schema."
                            ),
                        },
                    ]
                )

    return result


async def pending(
    session: AsyncSession,
    version: str,
    limit: int = 0,
    retry_failed: bool = False,
) -> list[Document]:
    """Find CGWB PDF documents that need extraction or a retry."""
    extraction = Document.metadata_["extract"]

    needs_extraction = or_(
        extraction["prompt"].astext.is_(None),
        extraction["prompt"].astext != version,
    )

    if retry_failed:
        needs_extraction = or_(
            needs_extraction,
            extraction["error"].astext.is_not(None),
        )

    statement = (
        select(Document)
        .where(Document.doc_type == "pdf")
        .where(Document.source_url.startswith("https://cgwb.gov.in/"))
        .where(needs_extraction)
        .order_by(Document.id)
    )

    if limit > 0:
        statement = statement.limit(limit)

    rows = await session.execute(statement)
    return list(rows.scalars().all())


async def document_text(
    session: AsyncSession,
    document: Document,
    chars: int,
) -> str:
    """Load the first three parsed pages for a document."""
    statement = (
        select(Page.text).where(Page.document_id == document.id).order_by(Page.page_no).limit(3)
    )

    rows = await session.execute(statement)
    return "\n\n".join(rows.scalars().all())[:chars]


async def save(
    session: AsyncSession,
    document: Document,
    result: Extraction,
    version: str,
) -> None:
    """Merge extracted fields without replacing parser metadata."""
    metadata = dict(document.metadata_ or {})

    extraction_info = {
        "prompt": version,
        "model": result.model,
        "attempts": result.attempts,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "cost_inr": round(result.cost_inr, 6),
    }

    if result.record is None:
        extraction_info["error"] = "; ".join(result.errors or ["Extraction failed"])[:2000]
    else:
        fields = result.record.model_dump(mode="json")

        conflicts = RESERVED.intersection(fields)
        if conflicts:
            raise ValueError(f"Schema fields cannot overwrite reserved metadata: {conflicts}")

        metadata.update(fields)

    metadata["extract"] = extraction_info
    document.metadata_ = metadata

    await session.commit()


async def run(
    sessionmaker: async_sessionmaker,
    gateway: LLMGateway,
    schema: type[BaseModel],
    prompt: str,
    version: str,
    *,
    limit: int = 0,
    rpm: int = 12,
    chars: int = 6000,
    retry_failed: bool = False,
    native: bool = False,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    echo: Callable[[str], None] = print,
) -> Counter:
    """Extract metadata from pending CGWB documents."""
    conflicts = RESERVED.intersection(schema.model_fields)

    if conflicts:
        raise ValueError(f"Schema uses reserved metadata fields: {conflicts}")

    if rpm < 1:
        raise ValueError("rpm must be at least 1")

    stats = Counter()

    async with sessionmaker() as session:
        documents = await pending(
            session,
            version,
            limit,
            retry_failed,
        )

        stats["pending"] = len(documents)
        echo(f"Found {len(documents)} documents to process.")

        for index, document in enumerate(documents, start=1):
            text = await document_text(session, document, chars)

            if not text.strip():
                stats["failed"] += 1
                echo(f"[{index}] {document.title}: no parsed page text")
                continue

            try:
                result = await extract(
                    gateway,
                    schema,
                    prompt,
                    version,
                    document.title,
                    text,
                    native_schema=native,
                )

            except LLMUnavailable as error:
                echo(f"LLM unavailable: {error}")
                echo("Waiting 60 seconds before one retry.")
                await sleep(60)

                try:
                    result = await extract(
                        gateway,
                        schema,
                        prompt,
                        version,
                        document.title,
                        text,
                        native_schema=native,
                    )
                except LLMUnavailable as second_error:
                    echo(f"Stopping: {second_error}")
                    break

            await save(session, document, result, version)

            stats["tokens_in"] += result.tokens_in
            stats["tokens_out"] += result.tokens_out
            stats["micro_inr"] += round(result.cost_inr * 1_000_000)

            if result.record is None:
                stats["failed"] += 1
                echo(f"[{index}] FAILED: {document.title}")
            else:
                stats["ok"] += 1
                if result.attempts > 1:
                    stats["repaired"] += 1
                echo(f"[{index}] OK: {document.title} (attempts={result.attempts})")

            if index < len(documents):
                await sleep(60 / rpm)

    return stats
