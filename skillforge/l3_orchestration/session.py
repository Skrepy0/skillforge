"""会话状态：创建、合并已采集字段、查询。"""

from __future__ import annotations

import uuid

from skillforge.l3_orchestration.session_store import InMemorySessionStore, SessionStore
from skillforge.shared.types import SessionState


class SessionManager:
    def __init__(self, store: SessionStore | None = None) -> None:
        self.store = store if store is not None else InMemorySessionStore()

    def get_or_create(self, skill: str, session_id: str | None) -> SessionState:
        session = self.store.get(session_id) if session_id else None
        return session if session is not None and session.skill == skill else self.create(skill)

    def create(self, skill: str) -> SessionState:
        session = SessionState(session_id=str(uuid.uuid4()), skill=skill)
        self.store.save(session)
        return session

    def merge(self, session: SessionState, updates: dict[str, str]) -> None:
        for key, value in updates.items():
            if value and value.strip():
                session.collected[key] = value.strip()
        self.store.save(session)

    def set_drafts(self, session: SessionState, drafts: dict[str, str]) -> None:
        session.drafts = dict(drafts)
        self.store.save(session)

    def bump_rewrite(self, session: SessionState) -> None:
        session.rewrite_rounds += 1
        self.store.save(session)

    def is_ready(self, session: SessionState, required: list[str]) -> bool:
        return all(session.collected.get(f, "").strip() for f in required)
