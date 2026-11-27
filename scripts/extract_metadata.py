"""Extract structured metadata from parsed AquiferAsk documents.

Examples:
    uv run python scripts/extract_metadata.py --limit 5
    uv run python scripts/extract_metadata.py
    uv run python scripts/extract_metadata.py --limit 5 --retry-failed
"""

import argparse
import asyncio
import sys
from pathlib import Path

from aquiferask.config import get_settings
from aquiferask.db.llm_calls import make_recorder
from aquiferask.db.session import make_engine, make_sessionmaker
from aquiferask.llm.doc_meta import DocMeta
from aquiferask.llm.extract import run
from aquiferask.llm.gateway import build_gateway
from aquiferask.llm.prompts import latest, read_prompt

PROMPTS = Path("prompts")


async def run_script(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)
    gateway = build_gateway(
        settings,
        recorder=make_recorder(sessionmaker),
    )

    try:
        version = latest(PROMPTS, "extract")
        prompt = read_prompt(PROMPTS, version)

        print(f"Prompt: {version}")
        print(f"Schema: {DocMeta.__name__}")
        print(f"Document limit: {args.limit or 'all'}")
        print()

        stats = await run(
            sessionmaker,
            gateway,
            DocMeta,
            prompt,
            version,
            limit=args.limit,
            rpm=args.rpm,
            chars=args.chars,
            retry_failed=args.retry_failed,
            native=args.native,
        )

        print("\n--- Extraction summary ---")
        for key, value in sorted(stats.items()):
            if key == "micro_inr":
                print(f"cost_inr: {value / 1_000_000:.6f}")
            else:
                print(f"{key}: {value}")

        return 0 if stats["failed"] == 0 else 1

    finally:
        for provider in gateway.providers:
            await provider._client.aclose()
        await engine.dispose()


def main() -> int:
    sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="extract at most N documents (0 means all)",
    )
    parser.add_argument(
        "--rpm",
        type=int,
        default=12,
        help="maximum extraction requests per minute",
    )
    parser.add_argument(
        "--chars",
        type=int,
        default=6000,
        help="maximum document characters sent to the model",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="retry documents with previous extraction errors",
    )
    parser.add_argument(
        "--native",
        action="store_true",
        help="request native JSON Schema output from the provider",
    )

    args = parser.parse_args()

    if args.limit < 0:
        parser.error("--limit must be zero or greater")
    if args.rpm < 1:
        parser.error("--rpm must be at least 1")
    if args.chars < 1:
        parser.error("--chars must be greater than zero")

    return asyncio.run(run_script(args))


if __name__ == "__main__":
    raise SystemExit(main())
