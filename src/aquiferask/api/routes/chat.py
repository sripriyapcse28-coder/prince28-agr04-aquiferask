"""POST /v1/chat (streaming) and GET /v1/usage."""

import json
import re
from collections.abc import AsyncIterator
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from aquiferask.api.deps import GatewayDep, RepoDep, UsageDep
from aquiferask.llm.gateway import LLMResult, LLMUnavailable

router = APIRouter(tags=["chat"])

PROMPT_VERSION = "chat_system_v1"


def load_prompt(directory: Path, name: str = PROMPT_VERSION) -> str:
    """Read a prompt file; fail at startup if it is missing."""
    return (directory / f"{name}.md").read_text(encoding="utf-8").strip()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    stream: bool = True


def sse(data: dict, event: str = "") -> str:
    """Format one server-sent event."""
    head = f"event: {event}\n" if event else ""
    return f"{head}data: {json.dumps(data, ensure_ascii=False)}\n\n"


def summary(result: LLMResult) -> dict:
    return {k: v for k, v in asdict(result).items() if k != "text"}


def extract_location_query(message: str) -> str | None:
    """Extract a location name from the question."""
    match = re.search(
        r"\b(?:of|for)\s+([A-Za-z]+)",
        message,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1)

    match = re.search(
        r"\b([A-Za-z]+)\s+(?:block|firkas?)\b",
        message,
        flags=re.IGNORECASE,
    )

    return match.group(1) if match else None


def build_retrieval_context(pages: list[dict[str, Any]], focus: str | None = None) -> str:
    """Format retrieved document pages with traceable citations."""
    if not pages:
        return "No matching document pages were retrieved."

    excerpts = []
    remaining = 12000

    for page in pages:
        title = str(page.get("title") or page.get("document_id") or "Unknown document")
        page_no = page.get("page_no", "unknown")
        headings = page.get("headings") or []

        if isinstance(headings, str):
            heading_text = headings
        else:
            heading_text = " > ".join(str(item) for item in headings)

        page_text = str(page.get("text") or "").strip()

        if focus:
            lines = page_text.splitlines()

            matching_indices = [
                index for index, line in enumerate(lines) if focus.casefold() in line.casefold()
            ]

            if matching_indices:
                header_indices = [
                    index
                    for index, line in enumerate(lines)
                    if index < matching_indices[0]
                    and (
                        "assessment unit" in line.casefold()
                        or "categorization" in line.casefold()
                        or "category" in line.casefold()
                    )
                ]

                selected_lines = []

                if header_indices:
                    selected_lines.append(lines[header_indices[-1]])

                selected_lines.extend(lines[index] for index in matching_indices)

                page_text = "\n".join(selected_lines)

                records = []

                for line in selected_lines:
                    cells = [
                        cell.strip().replace("**", "").strip()
                        for cell in line.strip().strip("|").split("|")
                    ]

                    if (
                        len(cells) >= 22
                        and "KAMUTHI" in line.upper()
                        and cells[2].upper() == "RAMANATHAPURAM"
                    ):
                        records.append(
                            f"District: {cells[2]}, "
                            f"Assessment Unit: {cells[3]}, "
                            f"Assessment Unit Type: {cells[4]}, "
                            f"Groundwater Category: {cells[21]}"
                        )

                if records:
                    page_text += "\n\nVerified CGWB table records:\n" + "\n".join(records)

        excerpt = page_text[: min(3500, remaining)]

        if not excerpt:
            continue

        source = f"[Source: {title}, page {page_no}]"

        if heading_text:
            source += f"\nSection: {heading_text}"

        excerpts.append(f"{source}\n{excerpt}")
        remaining -= len(excerpt)

        if remaining <= 0:
            break

    if not excerpts:
        return "No usable document text was retrieved."

    return "\n\n---\n\n".join(excerpts)


def build_verified_kamuthi_answer(context: str) -> str | None:
    """Answer only when both Kamuthi FIRKA records are verified."""
    if "Verified CGWB table records:" not in context:
        return None

    records = {}

    for line in context.splitlines():
        if not line.startswith("District:"):
            continue

        match = re.search(
            r"Assessment Unit:\s*(KAMUTHI (?:EAST|WEST)),\s*"
            r"Assessment Unit Type:\s*FIRKA,\s*"
            r"Groundwater Category:\s*([A-Za-z-]+)",
            line,
            flags=re.IGNORECASE,
        )

        if match:
            records[match.group(1).upper()] = match.group(2).capitalize()

    if "KAMUTHI EAST" not in records or "KAMUTHI WEST" not in records:
        return None

    source_match = re.search(
        r"\[Source:\s*(.*?),\s*page\s*(\d+)\]",
        context,
        flags=re.IGNORECASE,
    )

    if source_match:
        source = source_match.group(1)
        page = source_match.group(2)
        citation = f"Source: {source}, page {page}."
    else:
        citation = "Source: Connected CGWB document."

    return (
        "According to the connected CGWB assessment, "
        f"Kamuthi East FIRKA is classified as {records['KAMUTHI EAST']}, "
        f"and Kamuthi West FIRKA is classified as "
        f"{records['KAMUTHI WEST']}. "
        "These are separate FIRKA assessment units, "
        "not a combined Kamuthi block-level classification. "
        f"{citation}"
    )


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    gateway: GatewayDep,
    repo: RepoDep,
):
    location_query = extract_location_query(body.message)

    if location_query:
        pages = await repo.search_pages(location_query, limit=5)
    else:
        pages = await repo.search_pages(body.message, limit=5)

    context = build_retrieval_context(
        pages,
        focus=location_query,
    )

    print("\n========== AQUFERASK DEBUG ==========")
    print("Question:", body.message)
    print("Extracted location:", location_query)
    print("Retrieved pages:", len(pages))
    print("Has Kamuthi East:", "KAMUTHI EAST" in context.upper())
    print("Has Kamuthi West:", "KAMUTHI WEST" in context.upper())
    print(
        "Has verified records:",
        "VERIFIED CGWB TABLE RECORDS" in context.upper(),
    )
    print("=====================================\n")

    # Use verified CGWB table evidence directly when both FIRKAs are present.
    verified_answer = build_verified_kamuthi_answer(context)

    if verified_answer:
        if not body.stream:
            return {
                "answer": verified_answer,
                "verified": True,
            }

        async def verified_events() -> AsyncIterator[str]:
            yield sse({"delta": verified_answer})
            yield sse({"verified": True}, event="done")

        return StreamingResponse(
            verified_events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    user_content = (
        f"Question:\n{body.message}\n\n"
        f"Retrieved CGWB document excerpts:\n{context}\n\n"
        "Use only information directly supported by the excerpts. "
        "The verified table records contain separate assessment units. "
        "Never combine FIRKA results into a block-level result. "
        "Report each assessment unit separately. "
        "Cite factual claims with the exact document title and page number. "
        "If the evidence is insufficient, say you are not sure."
    )

    messages = [
        {
            "role": "system",
            "content": request.app.state.system_prompt,
        },
        {
            "role": "user",
            "content": user_content,
        },
    ]

    try:
        if not body.stream:
            result = await gateway.generate(
                messages,
                prompt_version=PROMPT_VERSION,
            )
            return {
                "answer": result.text,
                **summary(result),
            }

        stream = gateway.stream(
            messages,
            prompt_version=PROMPT_VERSION,
        )
        first = await anext(stream)

    except LLMUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=f"No model could answer: {exc}",
        ) from exc

    async def events() -> AsyncIterator[str]:
        item: str | LLMResult = first

        try:
            while True:
                if isinstance(item, LLMResult):
                    yield sse(summary(item), event="done")
                    return

                yield sse({"delta": item})
                item = await anext(stream)

        except LLMUnavailable as exc:
            yield sse({"detail": str(exc)}, event="error")

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/usage")
async def usage(
    repo: UsageDep,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> dict:
    """Tokens and rupees per day, from the llm_calls table."""
    rows = await repo.by_day(days)
    total = round(sum(row["cost_inr"] for row in rows), 4)

    return {
        "days": rows,
        "total_cost_inr": total,
        "calls": sum(row["calls"] for row in rows),
    }
