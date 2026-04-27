"""Logging configuration - console handler with plain or JSON format."""
import json
import logging
import sys
from logging.config import dictConfig

from .config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for k, v in record.__dict__.items():
            if k in ("args", "msg", "levelname", "levelno", "pathname", "filename",
                     "module", "exc_info", "exc_text", "stack_info", "lineno",
                     "funcName", "created", "msecs", "relativeCreated", "thread",
                     "threadName", "processName", "process", "name"):
                continue
            payload[k] = v
        return json.dumps(payload, default=str)


def setup_logging() -> None:
    formatter = "json" if settings.LOG_JSON else "plain"
    dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "plain": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            },
            "json": {"()": JsonFormatter},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": formatter,
            },
        },
        "root": {
            "level": settings.LOG_LEVEL,
            "handlers": ["console"],
        },
        "loggers": {
            "uvicorn.error": {"level": settings.LOG_LEVEL},
            "uvicorn.access": {"level": settings.LOG_LEVEL},
            "sqlalchemy.engine": {"level": "WARNING"},
            "apscheduler": {"level": "INFO"},
        },
    })


logger = logging.getLogger("hobb")
