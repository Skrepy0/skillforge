import json

import pytest
from skillforge.l3_orchestration.orchestrator import Orchestrator
from skillforge.l4_interface import cli, llm_client
from skillforge.shared.types import GateResult


@pytest.mark.parametrize("save", [False, True])
def test_markdown_cli_output(monkeypatch, tmp_path, capsys, save):
    class LocalLLM:
        def complete(self, prompt):
            return "可见的生成正文"

    orch = Orchestrator.from_config(llm=LocalLLM())
    monkeypatch.setattr(orch, "_output_root", lambda: tmp_path)
    monkeypatch.setattr(orch.gates, "run", lambda *a: GateResult(True, 1.0, 0.8))
    monkeypatch.setattr(llm_client, "OpenAICompatibleClient", LocalLLM)
    monkeypatch.setattr(Orchestrator, "from_config", lambda **kw: orch)
    payload = {"request": "test 测试", "collected": {"topic": "示例"}}
    if save:
        payload["out_path"] = "result.md"
    source = tmp_path / "input.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    assert (
        cli.main(
            ["run", "--skill", "test-skill", "--input", str(source), "--output-dir", str(tmp_path)]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "可见的生成正文" in output
    assert "## 概述" in output
    if save:
        assert "可见的生成正文" in (tmp_path / "result.md").read_text(encoding="utf-8")
    else:
        assert not (tmp_path / "result.md").exists()
