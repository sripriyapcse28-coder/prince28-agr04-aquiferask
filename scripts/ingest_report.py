"""Generate an ingestion report from the AquiferAsk database."""

import asyncio
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from aquiferask.config import get_settings
from aquiferask.db.session import make_engine


async def main() -> None:
    engine = make_engine(get_settings())

    try:
        async with engine.connect() as conn:
            documents = await conn.scalar(text("SELECT COUNT(*) FROM documents"))
            pages = await conn.scalar(text("SELECT COUNT(*) FROM pages"))
            characters = await conn.scalar(
                text("SELECT COALESCE(SUM(char_length(text)), 0) FROM pages")
            )
            dead_letter = await conn.scalar(text("SELECT COUNT(*) FROM parse_failures"))

            doc_types = (
                await conn.execute(
                    text(
                        "SELECT doc_type, COUNT(*) FROM documents "
                        "GROUP BY doc_type ORDER BY doc_type"
                    )
                )
            ).all()

            statuses = (
                await conn.execute(
                    text(
                        "SELECT status, COUNT(*) FROM ingest_items GROUP BY status ORDER BY status"
                    )
                )
            ).all()

        documents = documents or 0
        pages = pages or 0
        characters = characters or 0
        dead_letter = dead_letter or 0
        estimated_tokens = (characters + 3) // 4

        lines = [
            "# AquiferAsk Ingestion Report",
            "",
            f"- Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
            f"- Documents: {documents}",
            f"- Pages: {pages}",
            f"- Extracted text characters: {characters:,}",
            f"- Estimated tokens (characters / 4): {estimated_tokens:,}",
            f"- Dead-letter files (parse_failures): {dead_letter}",
            "",
            "## Documents by type",
            "",
            "| Document type | Count |",
            "|---|---:|",
        ]

        lines.extend(f"| {doc_type} | {count} |" for doc_type, count in doc_types)

        lines.extend(
            [
                "",
                "## Ingestion item statuses",
                "",
                "| Status | Count |",
                "|---|---:|",
            ]
        )

        lines.extend(f"| {status} | {count} |" for status, count in statuses)

        lines.extend(
            [
                "",
                "## Notes",
                "",
                "Token count is an estimate based on extracted text characters "
                "divided by 4, not an exact tokenizer count.",
                "",
            ]
        )

        output = Path("docs/INGEST_REPORT.md")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(lines), encoding="utf-8")

        print(
            f"documents={documents} pages={pages} dead_letter={dead_letter} -> {output.as_posix()}"
        )

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
