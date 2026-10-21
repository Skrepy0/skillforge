"""门禁编排：按 gates.yaml 执行规则，输出结构化 GateResult。"""

from __future__ import annotations

from skillforge.l1_governance import observability, scoring
from skillforge.l1_governance.rules import RULES
from skillforge.shared.config import GatesConfig
from skillforge.shared.logger import get_logger
from skillforge.shared.types import (
    DraftDocument,
    GateFailure,
    GateResult,
    SessionState,
    SkillContract,
)

logger = get_logger("skillforge.l1")


class GateRunner:
    def __init__(self, config: GatesConfig) -> None:
        self.config = config

    def run(
        self,
        draft: DraftDocument,
        contract: SkillContract,
        session: SessionState,
        trace_id: str = "",
    ) -> GateResult:
        results_by_rule: dict[str, list[GateFailure]] = {}

        for rule_name, check_fn in RULES.items():
            cfg = self.config.rules.get(rule_name, {})
            if not cfg.get("enabled", False):
                continue
            try:
                results_by_rule[rule_name] = check_fn(draft, contract, session, cfg)
            except Exception as exc:  # 单条规则异常不阻断整轮门禁
                logger.warning(
                    "gate.rule_error",
                    extra={
                        "trace_id": trace_id,
                        "session_id": session.session_id,
                        "layer": "l1",
                        "rule": rule_name,
                        "error": str(exc),
                    },
                )
                results_by_rule[rule_name] = [
                    GateFailure(
                        rule=rule_name,
                        section="（全文）",
                        evidence=f"规则执行异常：{exc}",
                        severity="warning",
                    )
                ]

        result = scoring.compute(self.config.rules, results_by_rule, self.config.pass_threshold)
        observability.log_gate_result(logger, trace_id, session.session_id, result)
        return result
