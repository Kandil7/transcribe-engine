"""Structured JSON logs (S20, design: المراقبة).

One JSON object per line. Fields come from `extra=` on each log call: `job_id`, `tenant_id`,
`stage`, `attempt`, and counts or ids. The formatter writes only those fields, the level, the logger
name and the message the call gives. It never writes the transcript, a file name or audio content,
and for an exception it writes the exception type, not its message, which can carry content.
"""

import json
import logging
import sys
import time
from typing import Any, TextIO

__all__ = ["JsonFormatter", "configure_logging", "json_handler", "quiet_transport_loggers"]

# Attributes every LogRecord has. Anything else on a record came from `extra=` and is logged.
_STANDARD_ATTRIBUTES = frozenset(
    vars(logging.LogRecord("", logging.INFO, "", 0, "", (), None)).keys() | {"message", "asctime"}
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRIBUTES and not key.startswith("_"):
                payload[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc_type"] = record.exc_info[0].__name__
        return json.dumps(payload, default=str, ensure_ascii=False, sort_keys=True)


def json_handler(stream: TextIO) -> logging.Handler:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    return handler


# httpx logs every request URL at INFO. A webhook URL can carry a token in its query, so the
# transport loggers stay at WARNING (S20, D-053).
_QUIET_LOGGERS = ("httpx", "httpcore")


def quiet_transport_loggers() -> None:
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def configure_logging(level: int = logging.INFO) -> None:
    """Replace the root handlers with one JSON handler on stderr. Called by the entry points."""
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(json_handler(sys.stderr))
    root.setLevel(level)
    quiet_transport_loggers()
