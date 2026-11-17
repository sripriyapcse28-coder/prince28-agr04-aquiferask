"""Load and access document records."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DocumentStore:
    """A simple JSON-backed document store."""

    def __init__(self, data_file: Path):
        self.data_file = data_file
        self.records: list[dict[str, Any]] = []

    def load(self) -> None:
        """Load records from the JSON file."""

        if not self.data_file.exists():
            raise FileNotFoundError(f"Data file not found: {self.data_file}")

        with self.data_file.open("r", encoding="utf-8") as file:
            self.records = json.load(file)

        logger.info("records loaded", extra={"records": len(self.records)})

    def get_all(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return all records up to the given limit."""
        return self.records[:limit]

    def get_by_id(self, document_id: str) -> dict[str, Any] | None:
        """Find one document using its ID."""

        for record in self.records:
            if record.get("id") == document_id:
                return record

        return None
