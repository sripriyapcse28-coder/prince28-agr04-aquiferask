"""Command-line interface for the GenericFinder downloader."""

import argparse
import asyncio
import time
from pathlib import Path

from genericfinder.ingest.fetch import fetch_all, read_sources


def show_result(record: dict) -> None:
    """Print the result of one download."""
    status = record["status"]
    path = record.get("path", record.get("error", ""))
    size = record.get("bytes", 0) / 1024

    print(
        f"[{status:10}] {size:8.1f} kB  {path}",
        flush=True,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Download project documents politely and safely.")
    parser.add_argument(
        "source",
        choices=["urls"],
        help="Read URLs from data/sources.csv",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between requests to the same host (seconds).",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    sources_file = root / "data" / "sources.csv"

    sources = read_sources(sources_file)
    print(f"Found {len(sources)} sources.", flush=True)

    start = time.monotonic()

    try:
        counts = await fetch_all(
            sources,
            root=root,
            per_host_delay=args.delay,
            on_result=show_result,
        )
    except KeyboardInterrupt:
        print("\nStopped by user.", flush=True)
        return

    elapsed = time.monotonic() - start

    print(
        f"sources={len(sources)} "
        f"downloaded={counts['downloaded']} "
        f"skipped={counts['skipped']} "
        f"blocked={counts['blocked']} "
        f"failed={counts['failed']} "
        f"seconds={elapsed:.1f}",
        flush=True,
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
