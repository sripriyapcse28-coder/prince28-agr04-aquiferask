"""Parse every downloaded CGWB file into pages in Postgres.

Safe to run again: it only parses files that are not already parsed.

uv run python scripts/parse_corpus.py
uv run python scripts/parse_corpus.py --limit 1
uv run python scripts/parse_corpus.py --retry-failed
uv run python scripts/parse_corpus.py --retry-failed --ocr eng
"""

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

from aquiferask.config import get_settings
from aquiferask.db.session import make_engine, make_sessionmaker
from aquiferask.ingest.parse import ParsedDoc, ParseError, parse_file, parse_pdf_ocr
from aquiferask.ingest.store import (
    document_id,
    failed_paths,
    parsed_ids,
    save_document,
    save_failure,
)

MANIFEST = Path("data/manifest.jsonl")


def load_records() -> list[dict]:
    """Load unique, downloaded CGWB files that exist on disk."""
    latest: dict[str, dict] = {}

    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        latest[record["url"]] = record

    records = []
    seen: set[str] = set()

    for record in latest.values():
        if record.get("source", "").strip().casefold() != "cgwb":
            continue

        if record.get("status") != "downloaded":
            continue

        raw_path = record.get("path")
        if not raw_path:
            continue

        path = Path(raw_path)
        if not path.is_file():
            continue

        identity = record.get("sha256") or str(path.resolve())
        if identity in seen:
            continue

        seen.add(identity)
        records.append(record)

    return records


def parse_one(path: Path, ocr_language: str) -> ParsedDoc:
    """Parse normally; use OCR when requested for scanned PDFs."""
    try:
        return parse_file(path)
    except ParseError as error:
        if error.reason != "no_text_layer" or not ocr_language:
            raise

        return parse_pdf_ocr(path, ocr_language)


async def run(args: argparse.Namespace) -> int:
    records = load_records()

    engine = make_engine(get_settings())
    session_factory = make_sessionmaker(engine)

    counts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    pages = 0
    started = time.perf_counter()

    try:
        # Use a short-lived session to check existing documents.
        async with session_factory() as session:
            done = await parsed_ids(session)
            failed = await failed_paths(session)

        todo = []

        for record in records:
            doc_id = document_id(record["sha256"])

            if doc_id in done:
                counts["already_parsed"] += 1
            elif record["path"] in failed and not args.retry_failed:
                counts["failed_before"] += 1
            else:
                done.add(doc_id)
                todo.append(record)

        selected = todo[: args.limit] if args.limit > 0 else todo

        print(
            f"Found {len(records)} CGWB files; {len(selected)} new files selected for parsing.",
            flush=True,
        )

        # Parse files outside database sessions.
        for number, record in enumerate(selected, start=1):
            path = Path(record["path"])

            try:
                parsed = await asyncio.to_thread(
                    parse_one,
                    path,
                    args.ocr,
                )

            except ParseError as error:
                async with session_factory() as session:
                    await save_failure(session, record, error)

                counts["failed"] += 1
                reasons[error.reason] += 1

                print(
                    f"failed  {error.reason:<16} {record['path']}",
                    flush=True,
                )

            except Exception as error:
                async with session_factory() as session:
                    await save_failure(
                        session,
                        record,
                        ParseError(
                            "unexpected_error",
                            f"{type(error).__name__}: {error}",
                        ),
                    )

                counts["failed"] += 1
                reasons["unexpected_error"] += 1

                print(
                    f"failed  unexpected_error {record['path']}: {type(error).__name__}: {error}",
                    flush=True,
                )

            else:
                async with session_factory() as session:
                    await save_document(session, record, parsed)

                counts["parsed"] += 1
                pages += len(parsed.pages)

                print(
                    f"parsed  {len(parsed.pages):>4} pages  {record['path']}",
                    flush=True,
                )

            if number % 10 == 0:
                print(
                    f"... processed {number} of {len(selected)} files",
                    flush=True,
                )

    finally:
        await engine.dispose()

    took = time.perf_counter() - started

    summary = " ".join(f"{name}={count}" for name, count in sorted(counts.items()))

    print(f"files={len(records)} {summary} pages={pages} seconds={took:.1f}")

    if reasons:
        print(
            "failure reasons: "
            + ", ".join(f"{reason}={count}" for reason, count in reasons.most_common())
        )

    return 0


def main() -> int:
    sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="parse at most N new files",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="retry files that failed",
    )
    parser.add_argument(
        "--ocr",
        default="",
        metavar="LANG",
        help="OCR scanned PDFs, e.g. eng",
    )

    args = parser.parse_args()

    if args.limit < 0:
        parser.error("--limit must be zero or greater")

    if not MANIFEST.exists():
        print("data/manifest.jsonl not found: collect your corpus first (Day 6)")
        return 1

    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
