"""套话检测：命中禁用词即记一条失败。词表来自 gates.yaml，缺省用内置兜底。"""

from __future__ import annotations

from typing import Any

from skillforge.shared.types import DraftDocument, GateFailure, SessionState, SkillContract

# 兜底词表：配置未提供 phrases 时使用，保证规则单独可测
DEFAULT_PHRASES: tuple[str, ...] = ("内置敏感词",)


def _resolve_phrases(config: dict[str, Any]) -> tuple[str, ...]:
    raw = config.get("phrases")
    if not raw:
        return DEFAULT_PHRASES
    return tuple(str(p) for p in raw)


def check(
    draft: DraftDocument,
    contract: SkillContract,
    session: SessionState,
    config: dict[str, Any],
) -> list[GateFailure]:
    phrases = _resolve_phrases(config)
    failures: list[GateFailure] = []
    for section in draft.sections:
        body = section["body"]
        for phrase in phrases:
            if phrase in body:
                failures.append(
                    GateFailure(
                        rule="cliche_check",
                        section=section["heading"],
                        evidence=f"命中套话：{phrase}",
                    )
                )
    return failures
