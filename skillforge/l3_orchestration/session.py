"""会话状态：创建、合并已采集字段、查询。"""

from __future__ import annotations

import uuid

from skillforge.shared.types import SessionState


class SessionManager:
    def create(self, skill: str) -> SessionState:
        return SessionState(session_id=str(uuid.uuid4()), skill=skill)

    def merge(self, session: SessionState, updates: dict[str, str]) -> None:
        for key, value in updates.items():
            if value and value.strip():
                session.collected[key] = value.strip()

    def set_drafts(self, session: SessionState, drafts: dict[str, str]) -> None:
        session.drafts = dict(drafts)

    def bump_rewrite(self, session: SessionState) -> None:
        session.rewrite_rounds += 1

    def is_ready(self, session: SessionState, required: list[str]) -> bool:
        return all(session.collected.get(f, "").strip() for f in required)
