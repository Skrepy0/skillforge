import json
from pathlib import Path

from skillforge.l4_interface import cli
from skillforge.shared.errors import SkillForgeError


def test_validate_returns_0(monkeypatch):
    monkeypatch.setattr(cli, "_cmd_validate", lambda args: 0)
    assert cli.main(["validate"]) == 0


def test_skills_list_output(monkeypatch, capsys):
    fake = {
        "skills": [
            {"name": "a", "category": "x", "description": "d1"},
            {"name": "b", "category": "y", "description": "d2"},
        ]
    }
    original = Path.read_text

    def _patched(self, *a, **k):
        if self.name == "index.json":
            return json.dumps(fake)
        return original(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", _patched)
    assert cli.main(["skills", "list"]) == 0
    out = capsys.readouterr().out
    assert "a" in out and "d1" in out


def test_run_llm_init_failure_returns_2(monkeypatch, tmp_path):
    req = tmp_path / "req.json"
    req.write_text(json.dumps({"request": "hi"}), encoding="utf-8")

    from skillforge.l4_interface import llm_client

    monkeypatch.setattr(
        llm_client,
        "OpenAICompatibleClient",
        lambda *a, **k: (_ for _ in ()).throw(SkillForgeError("boom")),
    )
    assert cli.main(["run", "--skill", "s", "--input", str(req)]) == 2


def test_run_needs_input_returns_3(monkeypatch, tmp_path):
    req = tmp_path / "req.json"
    req.write_text(json.dumps({"request": "hi"}), encoding="utf-8")

    from skillforge.l3_orchestration import orchestrator as orch_mod
    from skillforge.l4_interface import llm_client

    class _Fake:
        @classmethod
        def from_config(cls, llm=None):
            return cls()

        def run(self, **kw):
            return {"status": "needs_input", "missing": ["x"]}

    monkeypatch.setattr(llm_client, "OpenAICompatibleClient", lambda *a, **k: object())
    monkeypatch.setattr(orch_mod.Orchestrator, "from_config", _Fake.from_config)
    assert cli.main(["run", "--skill", "s", "--input", str(req)]) == 3


def test_ask_interactively(monkeypatch):
    answers = iter(["v1", "v2"])
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))
    out = cli._ask_interactively(["title", "degree_level"])
    assert out == {"title": "v1", "degree_level": "v2"}


def test_run_agent_passes_skill_preview_and_assets(monkeypatch, tmp_path):
    from skillforge.l3_orchestration.orchestrator import Orchestrator
    from skillforge.l4_interface import llm_client

    req = tmp_path / "req.json"
    req.write_text(
        json.dumps({"request": "PPT", "assets": {"photo": "photo.png"}}), encoding="utf-8"
    )
    captured = {}

    class Fake:
        def run(self, **kwargs):
            captured.update(kwargs)
            return {"status": "needs_review"}

    monkeypatch.setattr(Orchestrator, "from_config", lambda **kwargs: Fake())
    monkeypatch.setattr(llm_client, "OpenAICompatibleClient", lambda: object())
    assert (
        cli.main(
            [
                "run",
                "--skill",
                "explicit-skill",
                "--input",
                str(req),
                "--pptx-agent",
                "--pptx-preview",
            ]
        )
        == 1
    )
    assert captured["skill_name"] == "explicit-skill"
    assert captured["pptx_agent"] and captured["pptx_preview"]
    assert captured["pptx_assets"]["photo"] == tmp_path / "photo.png"


def test_preview_requires_agent():
    import pytest

    with pytest.raises(SystemExit) as exc:
        cli.main(["run", "--skill", "x", "--input", "unused.json", "--pptx-preview"])
    assert exc.value.code == 2
