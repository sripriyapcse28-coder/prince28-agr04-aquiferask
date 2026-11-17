"""Standard API error responses using RFC 9457."""

from fastapi import Request
from fastapi.responses import JSONResponse


class DocumentNotFoundError(Exception):
    """Raised when a requested document does not exist."""

    def __init__(self, document_id: str):
        self.document_id = document_id
        super().__init__(f"No document with id '{document_id}'.")


def problem_response(
    request: Request,
    status: int,
    title: str,
    detail: str,
) -> JSONResponse:
    """Create a standard Problem Details response."""

    request_id = getattr(request.state, "request_id", None)

    content = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "request_id": request_id,
    }

    return JSONResponse(
        status_code=status,
        content=content,
        media_type="application/problem+json",
    )


async def document_not_found_handler(
    request: Request,
    exc: DocumentNotFoundError,
) -> JSONResponse:
    """Handle missing document errors."""

    return problem_response(
        request=request,
        status=404,
        title="Not Found",
        detail=str(exc),
    )


async def validation_exception_handler(
    request: Request,
    exc,
) -> JSONResponse:
    """Return validation errors in a consistent format."""

    errors = [
        {
            "field": ".".join(str(part) for part in error["loc"]),
            "message": error["msg"],
        }
        for error in exc.errors()
    ]

    return JSONResponse(
        status_code=422,
        content={"errors": errors},
    )
