"""格式校验：章节齐全、顺序正确、总字数在目标区间内。

字数目标优先级：
1. session.collected["target_word_count"]（用户显式提供）
2. config["default_word_count"]（gates.yaml 配置）
3. DEFAULT_WORD_COUNT（兜底，仅在配置缺失时使用）
"""

from __future__ import annotations

from typing import Any

from skillforge.shared.types import DraftDocument, GateFailure, SessionState, SkillContract

DEFAULT_WORD_COUNT = 1800
DEFAULT_TOLERANCE = 0.10


def _count_chars(text: str) -> int:
    """近似字数：去掉空白后按字符计。中文以字为主时足够准确。"""
    return len("".join(text.split()))


def _resolve_target(session: SessionState, config: dict[str, Any]) -> int:
    raw = session.collected.get("target_word_count", "").strip()
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return int(config.get("default_word_count", DEFAULT_WORD_COUNT))


def _resolve_tolerance(config: dict[str, Any]) -> float:
    try:
        value = float(config.get("tolerance", DEFAULT_TOLERANCE))
    except (TypeError, ValueError):
        return DEFAULT_TOLERANCE
    return value if 0 <= value < 1 else DEFAULT_TOLERANCE


def _check_sections(draft: DraftDocument, contract: SkillContract) -> list[GateFailure]:
    failures: list[GateFailure] = []
    actual = [s["heading"] for s in draft.sections]
    expected = contract.sections

    missing = [h for h in expected if h not in actual]
    for heading in missing:
        failures.append(
            GateFailure(
                rule="format_check",
                section=heading,
                evidence=f"缺少必需章节：{heading}",
            )
        )

    # 只在章节齐全时检查顺序，避免“缺一章”同时触发两条失败
    if not missing and actual != expected:
        failures.append(
            GateFailure(
                rule="format_check",
                section="（全文）",
                evidence=f"章节顺序与契约不一致：实际 {actual}，期望 {expected}",
            )
        )

    return failures


def _check_word_count(
    draft: DraftDocument, session: SessionState, config: dict[str, Any]
) -> list[GateFailure]:
    target = _resolve_target(session, config)
    tolerance = _resolve_tolerance(config)
    low = int(target * (1 - tolerance))
    high = int(target * (1 + tolerance))

    total = sum(_count_chars(s["body"]) for s in draft.sections)
    if low <= total <= high:
        return []

    return [
        GateFailure(
            rule="format_check",
            section="（全文）",
            evidence=f"总字数 {total}，目标 {target}，允许区间 [{low}, {high}]",
        )
    ]


def check(
    draft: DraftDocument,
    contract: SkillContract,
    session: SessionState,
    config: dict[str, Any],
) -> list[GateFailure]:
    return _check_sections(draft, contract) + _check_word_count(draft, session, config)
