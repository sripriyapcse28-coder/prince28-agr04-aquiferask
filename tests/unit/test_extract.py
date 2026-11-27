"""Structured document metadata extraction tests."""

import pytest
from pydantic import BaseModel, ValidationError

from aquiferask.llm.doc_meta import DocMeta
from aquiferask.llm.extract import (
    Extraction,
    explain,
    extract,
    parse_json,
    run,
    save,
)
from aquiferask.llm.gateway import FakeLLM, LLMGateway

VALID = {
    "doc_kind": "report",
    "year": 2025,
    "language": "en",
    "summary": "Groundwater assessment report for Tamil Nadu.",
    "topics": ["groundwater", "assessment"],
    "assessment_year": ["2024-25"],
    "district": ["Ramanathapuram"],
    "block": ["Kadaladi"],
    "category": ["Critical"],
    "recharge_mcm": ["12.5 MCM"],
}


def test_parse_json_accepts_markdown_fences():
    result = parse_json('```json\n{"district": "Chennai"}\n```')
    assert result == {"district": "Chennai"}


def test_parse_json_rejects_missing_json():
    with pytest.raises(ValueError, match="No JSON object"):
        parse_json("No JSON was returned.")


def test_explain_formats_validation_errors():
    with pytest.raises(ValidationError) as caught:
        DocMeta.model_validate({"doc_kind": "unknown"})

    message = explain(caught.value)
    assert message
    assert "language" in message or "doc_kind" in message


async def test_extract_accepts_valid_metadata():
    llm = FakeLLM(script=[__import__("json").dumps(VALID)])
    gateway = LLMGateway([llm])

    result = await extract(
        gateway,
        DocMeta,
        "Extract metadata.",
        "extract_v1",
        "Groundwater report",
        "Tamil Nadu groundwater report.",
    )

    assert result.record is not None
    assert result.record.district == ["Ramanathapuram"]
    assert result.attempts == 1


async def test_extract_retries_after_invalid_json():
    import json

    llm = FakeLLM(script=["not valid JSON", json.dumps(VALID)])
    gateway = LLMGateway([llm])

    result = await extract(
        gateway,
        DocMeta,
        "Extract metadata.",
        "extract_v1",
        "Groundwater report",
        "Tamil Nadu groundwater report.",
    )

    assert result.record is not None
    assert result.attempts == 2
    assert len(result.errors) == 1


async def test_extract_returns_failure_after_all_attempts():
    llm = FakeLLM(script=["invalid", "invalid", "invalid"])
    gateway = LLMGateway([llm])

    result = await extract(
        gateway,
        DocMeta,
        "Extract metadata.",
        "extract_v1",
        "Groundwater report",
        "Tamil Nadu groundwater report.",
    )

    assert result.record is None
    assert result.attempts == 3
    assert len(result.errors) == 3


async def test_save_merges_metadata_without_overwriting_parser_fields():
    class FakeDocument:
        metadata_ = {
            "source": "CGWB",
            "parser": "pymupdf",
            "pages": 10,
        }

    class FakeSession:
        committed = False

        async def commit(self):
            self.committed = True

    document = FakeDocument()
    session = FakeSession()
    result = Extraction(
        record=DocMeta.model_validate(VALID),
        attempts=1,
        errors=[],
        model="fake-model",
    )

    await save(session, document, result, "extract_v1")

    assert document.metadata_["source"] == "CGWB"
    assert document.metadata_["parser"] == "pymupdf"
    assert document.metadata_["pages"] == 10
    assert document.metadata_["district"] == ["Ramanathapuram"]
    assert document.metadata_["extract"]["prompt"] == "extract_v1"
    assert session.committed


async def test_run_rejects_reserved_metadata_fields():
    class BadSchema(BaseModel):
        source: str

    with pytest.raises(ValueError, match="reserved"):
        await run(
            None,
            None,
            BadSchema,
            "Extract metadata.",
            "extract_v1",
        )
