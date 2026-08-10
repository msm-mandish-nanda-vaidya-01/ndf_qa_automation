"""Logging setup: console + rotating file under ``logs/``.

Call :func:`setup_logging` once per process (the root ``conftest.py`` does this).
Everywhere else, use ``get_logger(__name__)``.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from lib.core.config.env_config import LOGS_ROOT

_CONSOLE_FORMAT = "%(asctime)s %(levelname)-8s %(name)-40s %(message)s"
_FILE_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(filename)s:%(lineno)d %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_SECRET_KEYS = ("password", "token", "secret", "authorization", "api_key", "access_key")

_configured = False


class _RedactFilter(logging.Filter):
    """Best-effort scrub of obvious credential values from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = str(record.msg)
        lowered = message.lower()
        if any(key in lowered for key in _SECRET_KEYS):
            record.msg = _redact(message)
            record.args = ()
        return True


def _redact(message: str) -> str:
    out = []
    for chunk in message.split():
        lowered = chunk.lower()
        if any(key in lowered for key in _SECRET_KEYS) and any(sep in chunk for sep in "=:"):
            sep = "=" if "=" in chunk else ":"
            head, _, _ = chunk.partition(sep)
            out.append(f"{head}{sep}***REDACTED***")
        else:
            out.append(chunk)
    return " ".join(out)


def setup_logging(level: int | str = logging.INFO, log_file: str = "run.log") -> None:
    global _configured
    if _configured:
        return

    LOGS_ROOT.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_CONSOLE_FORMAT, _DATE_FORMAT))
    console.addFilter(_RedactFilter())
    root.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        Path(LOGS_ROOT) / log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT, _DATE_FORMAT))
    file_handler.addFilter(_RedactFilter())
    root.addHandler(file_handler)

    # third-party noise
    for noisy in ("urllib3", "botocore", "boto3", "s3transfer", "pymongo", "opensearch", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
