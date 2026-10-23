import pytest
from skillforge.l3_orchestration.orchestrator import Orchestrator
from skillforge.shared.errors import RenderError
from skillforge.shared.paths import PathValidationError, resolve_output_path
from skillforge.shared.types import SessionPhase


def test_missing_llm_preserves_collection_and_fails_before_generation(monkeypatch):
    orch = Orchestrator.from_config()
    assert orch.run("unroutable")["status"] == "needs_clarification"
    pending = orch.run("test tests")
    assert pending["status"] == "needs_input"
    monkeypatch.setattr(orch.queue, "generate_all", lambda *args: pytest.fail("generation started"))
    with pytest.raises(NotImplementedError, match="未注入 LLMClient"):
        orch.run(session_id=pending["session_id"], collected={"topic": "example"})
    assert orch.sessions.store.get(pending["session_id"]).phase == SessionPhase.COLLECTING


@pytest.mark.parametrize("rooted", [False, True])
def test_cli_absolute_target(monkeypatch, tmp_path, rooted):
    orch = Orchestrator.from_config()
    monkeypatch.setattr(orch, "_output_root", lambda: tmp_path if rooted else None)
    path = tmp_path / "output.docx"
    assert orch._validate_render_target(path) == path
    with pytest.raises(RenderError):
        orch._validate_render_target(tmp_path / "output.pptx")
    with pytest.raises(RenderError):
        orch._validate_render_target(tmp_path / ".." / "output.docx")
    if rooted:
        with pytest.raises(RenderError):
            orch._validate_render_target(tmp_path.parent / "output.docx")


@pytest.mark.parametrize("path", ["../bad.docx", "wrong.txt", "a/b/c/d.docx"])
def test_shared_api_path_rejections(tmp_path, path):
    with pytest.raises(PathValidationError):
        resolve_output_path(path, tmp_path, require_root=True)


def test_api_absolute_rejection_and_expected_suffix(tmp_path):
    with pytest.raises(PathValidationError):
        resolve_output_path(tmp_path / "output.docx", tmp_path, require_root=True)
    with pytest.raises(PathValidationError):
        resolve_output_path("output.pptx", tmp_path, expected_suffix=".docx")


def test_api_reuses_orchestrator(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from skillforge.l4_interface.api import create_app
    from skillforge.shared.version import __version__

    class FakeLLM:
        def complete(self, prompt):
            return "text"

    original = Orchestrator.from_config
    instances = []

    def factory(cls, **kwargs):
        orch = original(**kwargs)
        instances.append(orch)
        return orch

    monkeypatch.setattr(Orchestrator, "from_config", classmethod(factory))
    app = create_app(llm=FakeLLM(), api_key="secret", rate_limit_per_minute=0)
    assert app.version == __version__
    with TestClient(app) as client:
        for _ in range(2):
            response = client.post(
                "/generate", json={"request": "test tests"}, headers={"X-API-Key": "secret"}
            )
            assert response.status_code == 200
            assert response.json()["status"] == "needs_input"
    assert instances == [app.state.orchestrator]
    assert app.state.orchestrator.sessions.store is app.state.session_store
