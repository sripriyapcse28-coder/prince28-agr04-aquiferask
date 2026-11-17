"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from aquiferask.api.errors import (
    DocumentNotFoundError,
    document_not_found_handler,
    validation_exception_handler,
)
from aquiferask.api.middleware import RequestContextMiddleware
from aquiferask.api.routes import documents, health
from aquiferask.config import Settings, get_settings
from aquiferask.logging_setup import setup_logging
from aquiferask.store import DocumentStore


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""

    settings = settings or get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = DocumentStore(settings.data_file)

        try:
            store.load()
        except FileNotFoundError:
            store.records = []

        app.state.store = store
        yield

    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)

    app.add_exception_handler(
        DocumentNotFoundError,
        document_not_found_handler,
    )

    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )

    app.include_router(health.router)
    app.include_router(documents.router)

    return app
