"""Command-line client for the AquiferAsk ingestion API."""

import argparse
import sys
import time

import httpx

from aquiferask.config import get_settings


def show(progress: dict) -> str:
    """Format the current ingestion progress."""
    counts = progress.get("counts", {})

    parts = " ".join(
        f"{name}={counts.get(name, 0)}"
        for name in ("queued", "running", "done", "skipped", "failed")
    )

    pages = progress.get("pages", 0)
    seconds = progress.get("seconds", 0)

    return f"{progress.get('status', 'unknown'):<9} {parts} pages={pages} {seconds:.0f}s"


def watch(client: httpx.Client, job_id: str, every: float) -> None:
    """Poll a job until ingestion finishes."""
    while True:
        response = client.get(f"/v1/ingest/{job_id}")
        response.raise_for_status()

        progress = response.json()
        print(show(progress), flush=True)

        if progress.get("status") == "finished":
            break

        time.sleep(every)

    dead_letter = progress.get("dead_letter", [])

    if dead_letter:
        print("\nDocuments that failed:")
        for item in dead_letter:
            print(f"- {item.get('path') or item.get('url')}: {item.get('error', 'Unknown error')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Start and monitor AquiferAsk document ingestion.")

    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="AquiferAsk API base URL.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of documents to ingest (1-2000).",
    )
    parser.add_argument(
        "--source",
        help="Optional source filter.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry previously failed documents.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch the job until it finishes.",
    )
    parser.add_argument(
        "--every",
        type=float,
        default=3.0,
        help="Seconds between progress checks.",
    )

    args = parser.parse_args()

    if not 1 <= args.limit <= 2000:
        parser.error("--limit must be between 1 and 2000.")

    if args.every <= 0:
        parser.error("--every must be greater than zero.")

    settings = get_settings()

    if not settings.admin_token:
        print(
            "Error: ADMIN_TOKEN is not configured.",
            file=sys.stderr,
        )
        return 1

    headers = {"X-Admin-Token": settings.admin_token}

    # Do not send source when it has not been specified.
    payload = {
        "limit": args.limit,
        "retry_failed": args.retry_failed,
    }

    if args.source is not None:
        payload["source"] = args.source

    try:
        with httpx.Client(
            base_url=args.url.rstrip("/"),
            headers=headers,
            timeout=30.0,
        ) as client:
            response = client.post(
                "/v1/ingest",
                json=payload,
            )

            if response.status_code not in (200, 202):
                print(
                    f"API error ({response.status_code}): {response.text}",
                    file=sys.stderr,
                )
                return 1

            result = response.json()
            job_id = result.get("job_id")

            if not job_id:
                print(result.get("detail", result))
                return 0

            print(f"Job started: {job_id}")

            if args.watch:
                watch(client, job_id, args.every)

            return 0

    except httpx.TransportError as exc:
        print(
            f"Could not connect to the API: {exc}",
            file=sys.stderr,
        )
        return 1

    except httpx.HTTPStatusError as exc:
        print(
            f"API request failed: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
