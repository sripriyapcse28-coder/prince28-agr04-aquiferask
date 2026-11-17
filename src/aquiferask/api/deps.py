"""FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Request

from aquiferask.store import DocumentStore


def get_store(request: Request) -> DocumentStore:
    """Return the application document store."""
    return request.app.state.store


StoreDep = Annotated[DocumentStore, Depends(get_store)]
