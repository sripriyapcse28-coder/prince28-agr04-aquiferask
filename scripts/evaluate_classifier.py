"""Evaluate classifier prompt versions against a labelled test dataset."""

import asyncio
import json
from pathlib import Path

from aquiferask.config import get_settings
from aquiferask.llm.classify import accuracy, classify, find_leaks
from aquiferask.llm.gateway import build_gateway
from aquiferask.llm.prompts import read_prompt, versions

DATASET = Path("tests/fixtures/classification.json")


async def main():
    settings = get_settings()
    gateway = build_gateway(settings)

    rows = json.loads(DATASET.read_text(encoding="utf-8"))
    questions = [row["question"] for row in rows]

    prompt_versions = versions(settings.prompts_dir, "classify")

    if not prompt_versions:
        raise RuntimeError("No classifier prompt versions found.")

    results = {}

    for version in prompt_versions:
        print(f"\n{'=' * 55}")
        print(f"Evaluating: {version}")
        print("=" * 55)

        prompt = read_prompt(settings.prompts_dir, version)

        leaks = find_leaks(prompt, questions)
        if leaks:
            print(f"WARNING: {len(leaks)} test question(s) found in prompt.")

        evaluated = []

        for index, row in enumerate(rows, start=1):
            try:
                got, result = await classify(
                    gateway,
                    prompt,
                    version,
                    row["question"],
                )

                evaluated.append(
                    {
                        "question": row["question"],
                        "label": row["label"],
                        "got": got,
                        "correct": got == row["label"],
                        "provider": result.provider,
                        "latency_ms": result.latency_ms,
                        "cost_inr": result.cost_inr,
                    }
                )

                status = "PASS" if got == row["label"] else "FAIL"

                print(
                    f"{index:02}/{len(rows)} "
                    f"{status} | expected={row['label']} "
                    f"got={got} | {result.latency_ms} ms"
                )

            except Exception as error:
                evaluated.append(
                    {
                        "question": row["question"],
                        "label": row["label"],
                        "got": "error",
                        "correct": False,
                        "error": str(error),
                    }
                )
                print(f"{index:02}/{len(rows)} ERROR: {error}")

        score = accuracy(evaluated)
        correct = sum(item["correct"] for item in evaluated)
        total_cost = sum(item.get("cost_inr", 0) for item in evaluated)

        results[version] = {
            "correct": correct,
            "total": len(rows),
            "accuracy": round(score * 100, 2),
            "cost_inr": round(total_cost, 6),
            "leaks": leaks,
            "details": evaluated,
        }

        print(f"\n{version}: {correct}/{len(rows)} correct")
        print(f"Accuracy: {score * 100:.2f}%")
        print(f"Estimated cost: Rs. {total_cost:.6f}")

    print("\n\nPROMPT COMPARISON")
    print("-" * 55)

    for version, result in results.items():
        print(f"{version:<15} {result['correct']}/{result['total']} ({result['accuracy']:.2f}%)")

    output = Path("reports/classifier-evaluation.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nDetailed results saved to: {output}")


if __name__ == "__main__":
    asyncio.run(main())
