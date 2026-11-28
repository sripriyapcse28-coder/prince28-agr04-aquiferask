"""App factory: build a fully wired FastAPI app from settings."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from aquiferask.api.errors import (
    DocumentNotFoundError,
    document_not_found_handler,
    http_exception_handler,
    validation_exception_handler,
)
from aquiferask.api.middleware import RequestContextMiddleware
from aquiferask.api.routes import chat, documents, health, ingest
from aquiferask.config import Settings, get_settings
from aquiferask.db.llm_calls import make_recorder
from aquiferask.db.session import make_engine, make_sessionmaker
from aquiferask.llm.gateway import build_gateway
from aquiferask.logging_setup import setup_logging

logger = logging.getLogger("aquiferask")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)
    engine = make_engine(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("starting", extra={"status": settings.app_env})
        worker = None

        if settings.worker_in_api:
            from aquiferask.workers.main import run_embedded

            worker = asyncio.create_task(run_embedded(settings))

        yield

        if worker:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker

        if getattr(app.state, "queue", None):
            await app.state.queue.close()

        await engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.system_prompt = chat.load_prompt(settings.prompts_dir)
    app.state.gateway = build_gateway(
        settings,
        make_recorder(app.state.sessionmaker),
    )

    app.add_middleware(RequestContextMiddleware)

    # Standard API error responses.
    app.add_exception_handler(
        DocumentNotFoundError,
        document_not_found_handler,
    )
    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )
    app.add_exception_handler(
        StarletteHTTPException,
        http_exception_handler,
    )

    # API routes.
    v1 = APIRouter(prefix="/v1")
    v1.include_router(documents.router)
    v1.include_router(chat.router)
    v1.include_router(ingest.router)

    app.include_router(health.router)
    app.include_router(v1)

    return app
