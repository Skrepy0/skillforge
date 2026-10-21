"""加权汇总：规则失败数 → 规则得分 → 加权总分 → 通过/打回。"""

from __future__ import annotations

from typing import Any

from skillforge.shared.types import GateFailure, GateResult

ERROR_PENALTY = 0.2


def _rule_score(failures: list[GateFailure]) -> float:
    errors = sum(1 for f in failures if f.severity == "error")
    return max(0.0, 1.0 - errors * ERROR_PENALTY)


def compute(
    rules_config: dict[str, dict[str, Any]],
    results_by_rule: dict[str, list[GateFailure]],
    pass_threshold: float,
) -> GateResult:
    weighted = 0.0
    total_weight = 0.0
    all_failures: list[GateFailure] = []

    for rule, failures in results_by_rule.items():
        cfg = rules_config.get(rule, {})
        if not cfg.get("enabled", True):
            continue
        weight = float(cfg.get("weight", 1.0))
        weighted += weight * _rule_score(failures)
        total_weight += weight
        all_failures.extend(failures)

    score = weighted / total_weight if total_weight else 1.0
    return GateResult(
        passed=score >= pass_threshold,
        score=round(score, 4),
        threshold=pass_threshold,
        failures=all_failures,
    )
