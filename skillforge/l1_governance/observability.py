"""门禁可观测性：结构化日志，每次门禁输出一行汇总。"""

from __future__ import annotations

import logging

from skillforge.shared.types import GateResult


def log_gate_result(
    logger: logging.Logger,
    trace_id: str,
    session_id: str,
    result: GateResult,
) -> None:
    logger.info(
        "gate.completed",
        extra={
            "trace_id": trace_id,
            "session_id": session_id,
            "layer": "l1",
            "passed": result.passed,
            "score": result.score,
            "threshold": result.threshold,
            "failure_count": len(result.failures),
            "rules_failed": sorted({f.rule for f in result.failures}),
        },
    )
