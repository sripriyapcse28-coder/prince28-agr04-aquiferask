"""Route a question before answering it.

docs       The documents can answer it.
personal   It needs live information or private user data.
off_topic  It is not about groundwater or AquiferAsk.
"""

import re

from aquiferask.llm.gateway import LLMGateway, LLMResult

LABELS = ("docs", "personal", "off_topic")


def build_messages(prompt: str, question: str) -> list[dict[str, str]]:
    """Put the user's question inside tags as data."""
    return [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": f"<question>\n{question.strip()}\n</question>",
        },
    ]


def parse_label(reply: str, labels: tuple[str, ...] = LABELS) -> str:
    """Accept exactly one valid label."""
    text = re.sub(r"off[\s-]+topic", "off_topic", reply.lower())
    found = {label for label in labels if re.search(rf"(?<![a-z_]){label}(?![a-z_])", text)}
    return found.pop() if len(found) == 1 else "invalid"


async def classify(
    gateway: LLMGateway,
    prompt: str,
    version: str,
    question: str,
) -> tuple[str, LLMResult]:
    result = await gateway.generate(
        build_messages(prompt, question),
        purpose="classify",
        prompt_version=version,
        temperature=0,
    )
    return parse_label(result.text), result


def accuracy(rows: list[dict]) -> float:
    """Calculate classification accuracy."""
    return sum(row["got"] == row["label"] for row in rows) / len(rows) if rows else 0.0


def find_leaks(prompt: str, questions: list[str]) -> list[str]:
    """Find test questions already present in the prompt."""
    text = " ".join(prompt.lower().split())
    return [question for question in questions if " ".join(question.lower().split()) in text]
