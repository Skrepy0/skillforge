"""重复率检测：单行重复次数（warning）与整章重复率（error）。"""

from __future__ import annotations

from collections import Counter
from typing import Any

from skillforge.shared.types import DraftDocument, GateFailure, SessionState, SkillContract

DEFAULT_MAX_REPEAT = 2
DEFAULT_MAX_RATIO = 0.3


def _normalize(line: str) -> str:
    return " ".join(line.split())


def _lines(body: str) -> list[str]:
    return [ln for ln in (_normalize(p) for p in body.splitlines()) if ln]


def check(
    draft: DraftDocument,
    contract: SkillContract,
    session: SessionState,
    config: dict[str, Any],
) -> list[GateFailure]:
    max_repeat = int(config.get("max_repeat", DEFAULT_MAX_REPEAT))
    max_ratio = float(config.get("max_ratio", DEFAULT_MAX_RATIO))
    failures: list[GateFailure] = []

    for section in draft.sections:
        lines = _lines(section["body"])
        if not lines:
            continue
        counter = Counter(lines)

        for line, count in counter.items():
            if count > max_repeat:
                failures.append(
                    GateFailure(
                        rule="repetition_check",
                        section=section["heading"],
                        evidence=f"行重复 {count} 次（上限 {max_repeat}）：{line[:30]}",
                        severity="warning",
                    )
                )

        repeated = sum(c for c in counter.values() if c > 1)
        ratio = repeated / len(lines)
        if ratio > max_ratio:
            failures.append(
                GateFailure(
                    rule="repetition_check",
                    section=section["heading"],
                    evidence=f"整章重复率 {ratio:.2f} 超过 {max_ratio}",
                    severity="error",
                )
            )
    return failures
