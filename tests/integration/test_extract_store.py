"""Extracted document metadata, saved to a real Postgres database."""

import uuid

import pytest
from sqlalchemy import delete, select

from aquiferask.config import Settings
from aquiferask.db.models import Document, Page, ParseFailure
from aquiferask.db.session import make_engine, make_sessionmaker
from aquiferask.ingest.parse import ParsedDoc, ParsedPage
from aquiferask.ingest.store import save_document
from aquiferask.llm.doc_meta import DocMeta
from aquiferask.llm.extract import Extraction, save


@pytest.fixture
async def session(database_url):
    engine = make_engine(
        Settings(
            app_env="ci",
            database_url=database_url,
            _env_file=None,
        )
    )
    async with make_sessionmaker(engine)() as db:
        await db.execute(delete(Page))
        await db.execute(delete(ParseFailure))
        await db.execute(delete(Document))
        await db.commit()
        yield db
    await engine.dispose()


async def test_extracted_metadata_is_saved_without_overwriting_parser_metadata(
    session,
):
    sha = uuid.uuid4().hex * 2

    source = {
        "url": f"https://example.org/{sha}.pdf",
        "source": "CGWB",
        "licence": "CC BY 4.0",
        "title": "Groundwater Assessment",
        "path": f"data/raw/example/{sha}.pdf",
        "sha256": sha,
    }

    parsed = ParsedDoc(
        parser="pymupdf",
        kind="pdf",
        title="Groundwater Assessment",
        pages=[
            ParsedPage(
                1,
                "# Groundwater Assessment\n\nTamil Nadu groundwater report.",
                [],
            )
        ],
    )

    await save_document(session, source, parsed)

    document = await session.scalar(select(Document))
    assert document is not None

    original_source = document.metadata_["source"]
    original_parser = document.metadata_["parser"]
    original_pages = document.metadata_["pages"]

    metadata = DocMeta.model_validate(
        {
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
    )

    result = Extraction(
        record=metadata,
        attempts=1,
        errors=[],
        model="fake-model",
    )

    await save(session, document, result, "extract_v1")
    await session.refresh(document)

    stored = document.metadata_

    assert stored["district"] == ["Ramanathapuram"]
    assert stored["block"] == ["Kadaladi"]
    assert stored["category"] == ["Critical"]

    assert stored["source"] == original_source
    assert stored["parser"] == original_parser
    assert stored["pages"] == original_pages

    assert stored["extract"]["prompt"] == "extract_v1"
    assert stored["extract"]["model"] == "fake-model"
