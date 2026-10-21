"""占位符残留检测：TODO、待补充、XXX、空方括号等。"""

from __future__ import annotations

from typing import Any

from skillforge.shared.types import DraftDocument, GateFailure, SessionState, SkillContract

DEFAULT_MARKERS: tuple[str, ...] = (
    "TODO",
    "待补充",
    "待完善",
    "XXX",
    "【】",
    "[待填写]",
)


def _resolve_markers(config: dict[str, Any]) -> tuple[str, ...]:
    raw = config.get("markers")
    if not raw:
        return DEFAULT_MARKERS
    return tuple(str(m) for m in raw if str(m))


def check(
    draft: DraftDocument,
    contract: SkillContract,
    session: SessionState,
    config: dict[str, Any],
) -> list[GateFailure]:
    markers = _resolve_markers(config)
    failures: list[GateFailure] = []
    for section in draft.sections:
        for marker in markers:
            if marker in section["body"]:
                failures.append(
                    GateFailure(
                        rule="placeholder_check",
                        section=section["heading"],
                        evidence=f"残留占位符：{marker}",
                        severity="error",
                    )
                )
    return failures
