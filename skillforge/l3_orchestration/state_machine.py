"""阶段迁移：事件驱动的显式状态机。"""

from __future__ import annotations

from skillforge.shared.errors import SkillForgeError
from skillforge.shared.types import SessionPhase, SessionState

TRANSITIONS: dict[SessionPhase, dict[str, SessionPhase]] = {
    SessionPhase.COLLECTING: {"info_ready": SessionPhase.GENERATING},
    SessionPhase.GENERATING: {
        "generate_done": SessionPhase.REVIEWING,
        "edit_complete": SessionPhase.DELIVERED,
        "edit_incomplete": SessionPhase.FALLBACK,
    },
    SessionPhase.REVIEWING: {
        "gate_pass": SessionPhase.DELIVERED,
        "gate_fail": SessionPhase.REWRITING,
        "gate_fail_limit": SessionPhase.FALLBACK,
    },
    SessionPhase.REWRITING: {"rewrite_done": SessionPhase.REVIEWING},
}


class StateMachine:
    def transition(self, session: SessionState, event: str) -> SessionPhase:
        allowed = TRANSITIONS.get(session.phase)
        if allowed is None or event not in allowed:
            raise SkillForgeError(f"非法迁移: 阶段 {session.phase.value} 不接受事件 {event}")
        session.phase = allowed[event]
        return session.phase
