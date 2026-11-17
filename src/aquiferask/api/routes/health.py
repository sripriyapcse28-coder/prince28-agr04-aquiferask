"""Health and readiness endpoints."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
def health():
    """Check whether the application is running."""
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request):
    """Check whether the application is ready."""

    store = request.app.state.store
    records_loaded = bool(store.records)

    if not records_loaded:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not ready",
                "checks": {
                    "records_loaded": False,
                },
            },
        )

    return {
        "status": "ready",
        "checks": {
            "records_loaded": True,
        },
    }
