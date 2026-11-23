"""Command-line interface for the GenericFinder downloader."""

import argparse
import asyncio
import hashlib
import mimetypes
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

from genericfinder.ingest.fetch import (
    KNOWN_EXT,
    Manifest,
    fetch_all,
    now_iso,
    read_sources,
)


def show_result(record: dict) -> None:
    """Print the result of one download."""
    status = record["status"]
    path = record.get("path", record.get("error", ""))
    size = record.get("bytes", 0) / 1024

    print(
        f"[{status:10}] {size:8.1f} kB  {path}",
        flush=True,
    )


def register_manual_files(
    folder: Path,
    root: Path,
    from_url: str,
    source: str,
    licence: str,
) -> tuple[int, int]:
    """Register manually downloaded files in the manifest."""
    raw_root = (root / "data" / "raw").resolve()
    folder = folder.resolve()

    if not folder.is_dir():
        raise ValueError(f"Folder does not exist: {folder}")

    if not folder.is_relative_to(raw_root):
        raise ValueError("Manual folder must be inside data/raw.")

    parsed = urlsplit(from_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--from-url must be a valid HTTP(S) URL.")

    manifest = Manifest(root / "data" / "manifest.jsonl")
    added = 0
    unchanged = 0

    files = sorted(
        path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in KNOWN_EXT
    )

    for path in files:
        resolved = path.resolve()

        if not resolved.is_relative_to(raw_root):
            continue

        relative = path.relative_to(root).as_posix()
        file_url = (
            from_url.split("#", 1)[0] + "#" + quote(path.relative_to(folder).as_posix(), safe="/")
        )

        if manifest.done(file_url, root):
            unchanged += 1
            continue

        digest = hashlib.sha256()
        size = 0

        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)

        record = {
            "url": file_url,
            "source": source,
            "licence": licence,
            "title": path.stem,
            "via": "manual",
            "path": relative,
            "bytes": size,
            "sha256": digest.hexdigest(),
            "content_type": (mimetypes.guess_type(path.name)[0] or "application/octet-stream"),
            "status": "downloaded",
            "fetched_at": now_iso(),
        }

        manifest.add(record)
        added += 1

    return added, unchanged


async def main() -> None:
    parser = argparse.ArgumentParser(description="Download and register project documents safely.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    urls_parser = subparsers.add_parser(
        "urls",
        help="Download URLs from data/sources.csv",
    )
    urls_parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between requests to the same host (seconds).",
    )

    manual_parser = subparsers.add_parser(
        "manual",
        help="Register files downloaded manually.",
    )
    manual_parser.add_argument("folder", help="Folder inside data/raw")
    manual_parser.add_argument("--from-url", required=True)
    manual_parser.add_argument("--source", required=True)
    manual_parser.add_argument("--licence", required=True)

    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent

    if args.command == "manual":
        added, unchanged = register_manual_files(
            root / args.folder,
            root,
            args.from_url,
            args.source,
            args.licence,
        )
        print(f"folder={args.folder} added={added} unchanged={unchanged}")
        return

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
