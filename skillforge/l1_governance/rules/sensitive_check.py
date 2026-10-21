"""敏感词检测：与 cliche_check 同构，词表独立，默认 error。"""

from __future__ import annotations

from typing import Any

from skillforge.shared.types import DraftDocument, GateFailure, SessionState, SkillContract

DEFAULT_WORDS: tuple[str, ...] = ()


def _resolve_words(config: dict[str, Any]) -> tuple[str, ...]:
    raw = config.get("words")
    if not raw:
        return DEFAULT_WORDS
    return tuple(str(w).strip() for w in raw if str(w).strip())


def check(
    draft: DraftDocument,
    contract: SkillContract,
    session: SessionState,
    config: dict[str, Any],
) -> list[GateFailure]:
    words = _resolve_words(config)
    if not words:
        return []

    severity = config.get("severity", "error")
    failures: list[GateFailure] = []
    for section in draft.sections:
        body = "".join(section["body"].split())
        seen: set[str] = set()
        for word in words:
            if word in body and word not in seen:
                seen.add(word)
                failures.append(
                    GateFailure(
                        rule="sensitive_check",
                        section=section["heading"],
                        evidence=f"命中敏感词：{word}",
                        severity=severity,
                    )
                )
    return failures
