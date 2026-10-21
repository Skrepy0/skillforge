"""结构化日志：JSON lines，必带 trace_id / session_id / layer。"""

from __future__ import annotations

import json
import logging
import sys

from skillforge.shared.config import LoggingConfig


class JsonFormatter(logging.Formatter):
    _EXTRA_KEYS = ("trace_id", "session_id", "layer")

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        for key in self._EXTRA_KEYS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str, config: LoggingConfig | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    level = (config.level if config else "INFO").upper()
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger
