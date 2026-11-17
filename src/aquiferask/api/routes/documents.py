"""Document API endpoints."""

from fastapi import APIRouter, Query

from aquiferask.api.deps import StoreDep
from aquiferask.api.errors import DocumentNotFoundError

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.get("")
def get_documents(
    store: StoreDep,
    limit: int = Query(default=100, ge=1, le=500),
    q: str | None = Query(default=None),
):
    """Return documents with optional search and pagination."""

    records = store.get_all(limit=500)

    if q:
        search_term = q.casefold()
        records = [
            record for record in records if search_term in record.get("title", "").casefold()
        ]

    return {
        "total": len(records),
        "items": records[:limit],
    }


@router.get("/{document_id}")
def get_document(
    document_id: str,
    store: StoreDep,
):
    """Return one document by ID."""

    document = store.get_by_id(document_id)

    if document is None:
        raise DocumentNotFoundError(document_id)

    return document
