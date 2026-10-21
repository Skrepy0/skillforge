"""结构化日志：JSON lines，自动包含所有 extra 字段，支持采样。"""

from __future__ import annotations

import json
import logging
import random
import sys

from skillforge.shared.config import LoggingConfig


class JsonFormatter(logging.Formatter):
    """把 LogRecord 序列化为单行 JSON。

    - 固定字段：level / logger / message / timestamp
    - extra 字段：除 logging 标准属性外，全部写入 payload
    - 值为 None 的 extra 跳过，避免污染下游解析
    - 不可序列化的值用 str() 兜底
    """

    def __init__(self) -> None:
        super().__init__()
        # LogRecord 标准属性由 logging 内部维护，不进入业务 payload
        self._reserved = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        for key, value in record.__dict__.items():
            if key in self._reserved or key.startswith("_"):
                continue
            if value is None:
                continue
            payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


class _SamplingFilter(logging.Filter):
    """按 sample_rate 采样；1.0 全留，0.0 全丢。"""

    def __init__(self, rate: float) -> None:
        super().__init__()
        self.rate = max(0.0, min(1.0, rate))

    def filter(self, record: logging.LogRecord) -> bool:
        if self.rate >= 1.0:
            return True
        if self.rate <= 0.0:
            return False
        return random.random() < self.rate


def get_logger(name: str, config: LoggingConfig | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    level = (config.level if config else "INFO").upper()
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    if config is not None and config.sample_rate < 1.0:
        handler.addFilter(_SamplingFilter(config.sample_rate))

    logger.addHandler(handler)
    logger.propagate = False
    return logger
