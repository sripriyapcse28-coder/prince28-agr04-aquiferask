"""Compare classifier prompt versions using a cached evaluation test set."""

import asyncio
import hashlib
import json
from pathlib import Path

from aquiferask.config import get_settings
from aquiferask.llm.classify import classify, find_leaks
from aquiferask.llm.gateway import build_gateway
from aquiferask.llm.prompts import read_prompt, versions

DATASET = Path("eval/prompt_testset.jsonl")
CACHE_DIR = Path("eval/cache")
NOTES = Path("NOTES.md")

START_MARKER = "<!-- PROMPT_COMPARISON_START -->"
END_MARKER = "<!-- PROMPT_COMPARISON_END -->"

RATE_LIMIT_SECONDS = 5


def load_dataset():
    rows = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]

    if len(rows) < 20:
        raise ValueError(f"Expected at least 20 questions, found {len(rows)}.")

    allowed = {"docs", "personal", "off_topic"}

    for index, row in enumerate(rows, start=1):
        if row.get("label") not in allowed or not row.get("question"):
            raise ValueError(f"Invalid test-set row: {index}")

    return rows


def cache_path(version, prompt, question):
    digest = hashlib.sha256(f"{version}\0{prompt}\0{question}".encode()).hexdigest()
    return CACHE_DIR / f"{version}-{digest}.json"


def update_notes(results):
    lines = [
        START_MARKER,
        "## Prompt comparison",
        "",
        "| Version | Correct | Total | Accuracy |",
        "|---|---:|---:|---:|",
    ]

    for version, result in results.items():
        lines.append(
            f"| {version} | {result['correct']} | {result['total']} | {result['accuracy']:.2f}% |"
        )

    lines.extend(["", "### Missed questions", ""])

    for version, result in results.items():
        misses = result["misses"]
        if not misses:
            lines.append(f"- **{version}:** No misses.")
            continue

        lines.append(f"- **{version}:**")
        for miss in misses:
            lines.append(
                f"  - Line {miss['line']}: expected "
                f"`{miss['expected']}`, got `{miss['got']}` — "
                f"{miss['question']}"
            )

    lines.extend([END_MARKER, ""])
    block = "\n".join(lines)

    existing = NOTES.read_text(encoding="utf-8-sig") if NOTES.exists() else ""

    if START_MARKER in existing and END_MARKER in existing:
        before = existing.split(START_MARKER, 1)[0]
        after = existing.split(END_MARKER, 1)[1]
        updated = before + block + after.lstrip("\n")
    else:
        updated = existing.rstrip() + "\n\n" + block

    NOTES.write_text(updated, encoding="utf-8")


async def main():
    rows = load_dataset()
    questions = [row["question"] for row in rows]

    settings = get_settings()
    gateway = build_gateway(settings)
    prompt_versions = versions(settings.prompts_dir, "classify")

    if not prompt_versions:
        raise RuntimeError("No classifier prompt versions found.")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    results = {}
    model_calls = 0
    cache_hits = 0

    for version in prompt_versions:
        prompt = read_prompt(settings.prompts_dir, version)
        leaks = find_leaks(prompt, questions)

        if leaks:
            print(f"LEAK in {version}: {leaks}")

        correct = 0
        misses = []

        print(f"\nEvaluating {version}...")

        for index, row in enumerate(rows, start=1):
            path = cache_path(version, prompt, row["question"])

            if path.exists():
                cached = json.loads(path.read_text(encoding="utf-8"))
                got = cached["got"]
                cache_hits += 1
                source = "CACHE"
            else:
                if model_calls:
                    await asyncio.sleep(RATE_LIMIT_SECONDS)

                try:
                    got, _ = await classify(
                        gateway,
                        prompt,
                        version,
                        row["question"],
                    )
                except Exception as error:
                    print(f"ERROR {version}, line {index}: {error}")
                    got = "error"
                else:
                    path.write_text(
                        json.dumps({"got": got}, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    model_calls += 1

                source = "MODEL"

            is_correct = got == row["label"]

            if is_correct:
                correct += 1
            else:
                miss = {
                    "line": index,
                    "question": row["question"],
                    "expected": row["label"],
                    "got": got,
                }
                misses.append(miss)
                print(
                    f"MISS {version} line {index}: "
                    f"expected {row['label']}, got {got} "
                    f"({row['question']})"
                )

            print(f"{source} {version} {index}/{len(rows)}: {'PASS' if is_correct else 'FAIL'}")

        total = len(rows)
        results[version] = {
            "correct": correct,
            "total": total,
            "accuracy": correct / total * 100,
            "misses": misses,
        }

    print("\nPROMPT COMPARISON")
    print("| Version | Correct | Total | Accuracy |")
    print("|---|---:|---:|---:|")

    for version, result in results.items():
        print(
            f"| {version} | {result['correct']} | {result['total']} | {result['accuracy']:.2f}% |"
        )

    print(f"\nModel calls made: {model_calls}")
    print(f"Cached answers reused: {cache_hits}")

    update_notes(results)
    print("Updated NOTES.md")


if __name__ == "__main__":
    asyncio.run(main())
