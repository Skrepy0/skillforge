from skillforge.l3_orchestration.session import SessionManager
from skillforge.l3_orchestration.session_store import InMemorySessionStore
from skillforge.shared.types import SessionState


def test_store_expiry_capacity_and_copy(monkeypatch):
    now = 0.0
    monkeypatch.setattr("skillforge.l3_orchestration.session_store.time.monotonic", lambda: now)
    store = InMemorySessionStore(ttl_seconds=10, max_sessions=2)
    original = SessionState("a", "skill")
    store.save(original)
    original.collected["x"] = "not saved"
    assert store.get("a").collected == {}
    store.save(SessionState("b", "skill"))
    store.save(SessionState("c", "skill"))
    assert store.get("a") is None
    now = 5.0
    store.save(SessionState("b", "skill"))
    now = 10.0
    assert store.get("c") is None
    assert store.get("b") is not None
    assert len(store._entries) == 1
    now = 15.0
    assert store.get("b") is None
    assert not store._entries


def test_manager_resume_and_save():
    store = InMemorySessionStore()
    manager = SessionManager(store)
    session = manager.create("skill")
    manager.merge(session, {"x": " value "})
    manager.set_drafts(session, {"section": "text"})
    manager.bump_rewrite(session)
    assert SessionManager(store).get_or_create("skill", session.session_id) == session
    assert manager.get_or_create("other", session.session_id).session_id != session.session_id
    assert manager.get_or_create("skill", "unknown").session_id != session.session_id
