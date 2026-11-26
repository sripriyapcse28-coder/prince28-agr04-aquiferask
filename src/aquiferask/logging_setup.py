"""Configure structured JSON logging."""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

# The id of the web request being handled. The LLM gateway stamps it on every llm_calls row.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    """Format log records as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in logging.LogRecord(
                name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None
            ).__dict__ and not key.startswith("_"):
                log_data[key] = value

        return json.dumps(log_data, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Configure the application's root logger."""

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
