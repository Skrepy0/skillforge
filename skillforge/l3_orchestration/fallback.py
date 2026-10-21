"""降级策略：澄清、追问、模板兜底。按异常类型分派。"""

from __future__ import annotations

from collections.abc import Callable

from skillforge.l3_orchestration.contract import question_for
from skillforge.shared.types import GateResult, RouteDecision, SessionState


class Fallback:
    def clarify(self, decision: RouteDecision) -> dict:
        options = [name for name, _ in decision.candidates]
        return {
            "status": "needs_clarification",
            "candidates": options,
            "message": "命中多个技能，请选择：" + "、".join(options)
            if options
            else "没有匹配的技能，请说明要写哪类文书。",
        }

    def ask(
        self,
        missing: list[str],
        ask_fn: Callable[[list[str]], dict[str, str]],
    ) -> dict[str, str]:
        return ask_fn(missing)

    def needs_input(self, missing: list[str]) -> dict:
        return {
            "status": "needs_input",
            "missing": missing,
            "questions": [question_for(f) for f in missing],
            "message": "信息不足，请补充以上字段后重试。",
        }

    def template(self, session: SessionState, result: GateResult) -> dict:
        body = "\n\n".join(
            f"## {heading}\n【待补充：门禁未通过，请人工补写】" for heading in session.drafts.keys()
        )
        return {
            "status": "fallback",
            "message": "门禁连续未通过，已降级为模板。失败原因见 gate.failures。",
            "gate": result,
            "draft_markdown": body,
        }
