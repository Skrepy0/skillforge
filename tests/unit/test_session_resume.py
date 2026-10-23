import pytest
from skillforge.l1_governance.gate_runner import GateRunner
from skillforge.l2_capability.loader import LoadedSkill, Loader
from skillforge.l3_orchestration.orchestrator import Orchestrator
from skillforge.l3_orchestration.session_store import InMemorySessionStore
from skillforge.shared.types import GateResult, SessionPhase, SkillContract


class FakeLLM:
    def complete(self, prompt):
        return "generated text"


@pytest.fixture
def setup_skill(monkeypatch):
    skill = LoadedSkill(
        SkillContract("test-skill", "", ["topic", "detail"], "markdown", ["Body"]), "", {}
    )
    monkeypatch.setattr(Loader, "load", lambda self, name: skill)
    monkeypatch.setattr(GateRunner, "run", lambda *args: GateResult(True, 1.0, 0.8))


def test_resume_across_orchestrators(setup_skill):
    store = InMemorySessionStore()
    first = Orchestrator.from_config(FakeLLM(), store).run("test tests", {"topic": "kept"})
    assert first["status"] == "needs_input"
    second = Orchestrator.from_config(FakeLLM(), store).run(
        session_id=first["session_id"], collected={"detail": "new"}
    )
    assert second["status"] == "delivered"
    assert second["session_id"] == first["session_id"]
    stored = store.get(first["session_id"])
    assert stored.collected == {"topic": "kept", "detail": "new"}
    assert stored.phase == SessionPhase.DELIVERED


@pytest.mark.parametrize("phase", [SessionPhase.DELIVERED, SessionPhase.FALLBACK])
def test_terminal_session_starts_fresh(setup_skill, phase):
    store = InMemorySessionStore()
    orch = Orchestrator.from_config(FakeLLM(), store)
    session = orch.sessions.create("test-skill")
    session.phase = phase
    store.save(session)
    result = orch.run(session_id=session.session_id)
    assert result["status"] == "needs_input"
    assert result["session_id"] != session.session_id


def test_api_resume(setup_skill):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from skillforge.l4_interface.api import create_app

    app = create_app(llm=FakeLLM(), api_key="secret", rate_limit_per_minute=0)
    with TestClient(app) as client:
        headers = {"X-API-Key": "secret"}
        first = client.post(
            "/generate",
            headers=headers,
            json={"request": "test tests", "collected": {"topic": "kept"}},
        )
        assert first.status_code == 200
        assert first.json()["status"] == "needs_input"
        sid = first.json()["session_id"]
        second = client.post(
            "/generate", headers=headers, json={"session_id": sid, "collected": {"detail": "new"}}
        )
        assert second.status_code == 200
        assert second.json()["status"] == "delivered"
        assert second.json()["session_id"] == sid
        assert app.state.session_store.get(sid).collected["topic"] == "kept"
