"""JsonFormatter：extra 字段保留、采样、level、handler 不重复。"""

from __future__ import annotations

import io
import json
import logging

from skillforge.shared.config import LoggingConfig
from skillforge.shared.logger import JsonFormatter, _SamplingFilter, get_logger


def _make_logger(level: str = "INFO") -> tuple[logging.Logger, io.StringIO]:
    name = f"test.logger.{id(object())}"
    logger = logging.getLogger(name)
    logger.handlers.clear()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger, stream


def _lines(stream: io.StringIO) -> list[dict]:
    return [json.loads(ln) for ln in stream.getvalue().strip().splitlines() if ln]


def test_extra_business_fields_preserved():
    logger, stream = _make_logger()
    logger.info(
        "gate.completed",
        extra={
            "trace_id": "t1",
            "session_id": "s1",
            "layer": "l1",
            "passed": True,
            "score": 0.5,
            "rules_failed": ["a", "b"],
        },
    )
    payload = _lines(stream)[0]
    assert payload["trace_id"] == "t1"
    assert payload["session_id"] == "s1"
    assert payload["layer"] == "l1"
    assert payload["passed"] is True
    assert payload["score"] == 0.5
    assert payload["rules_failed"] == ["a", "b"]


def test_standard_attributes_not_duplicated_in_payload():
    logger, stream = _make_logger()
    logger.info("evt", extra={"custom": 1})
    payload = _lines(stream)[0]

    # level 是 Formatter 主动写入的固定字段，不属于“重复”
    assert payload["level"] == "INFO"
    # LogRecord 的其余标准属性不应出现在 payload 里
    for key in (
        "levelno",
        "pathname",
        "filename",
        "module",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "process",
        "processName",
        "msg",
        "args",
        "exc_info",
        "stack_info",
    ):
        assert key not in payload, key
    assert payload["custom"] == 1


def test_none_extra_skipped():
    logger, stream = _make_logger()
    logger.info("evt", extra={"a": None, "b": 0})
    payload = _lines(stream)[0]
    assert "a" not in payload
    assert payload["b"] == 0


def test_unserializable_extra_becomes_str():
    logger, stream = _make_logger()
    logger.info("evt", extra={"obj": object()})
    payload = _lines(stream)[0]
    assert isinstance(payload["obj"], str)


def test_level_respected():
    logger, stream = _make_logger(level="WARNING")
    logger.info("skip-me")
    logger.warning("keep-me")
    lines = _lines(stream)
    assert len(lines) == 1
    assert lines[0]["message"] == "keep-me"


def test_get_logger_no_duplicate_handlers():
    name = f"test.dup.{id(object())}"
    l1 = get_logger(name, LoggingConfig())
    l2 = get_logger(name, LoggingConfig())
    assert l1 is l2
    assert len(l1.handlers) == 1


def test_sampling_filter_zero_and_one():
    record = logging.makeLogRecord({})
    assert _SamplingFilter(0.0).filter(record) is False
    assert _SamplingFilter(1.0).filter(record) is True
