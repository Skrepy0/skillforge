"""run_file 对 pptx 技能的默认输出文件名。"""

from __future__ import annotations

import json
from pathlib import Path

from skillforge.l3_orchestration.orchestrator import Orchestrator
from skillforge.shared.types import GateResult, RouteDecision


class _StubLLM:
    def complete(self, prompt: str) -> str:
        return "章节正文"


def _pass_result() -> GateResult:
    return GateResult(passed=True, score=1.0, threshold=0.8)


def _patched_contract(orch: Orchestrator, monkeypatch, output: str) -> None:
    """把 loader 返回的契约 output 改成指定值（frozen dataclass 用 setattr 绕过）。"""
    real_load_contract = orch.loader.load_contract
    real_load = orch.loader.load

    def _load_contract(name: str):
        c = real_load_contract(name)
        object.__setattr__(c, "output", output)
        return c

    def _load(name: str):
        loaded = real_load(name)
        object.__setattr__(loaded.contract, "output", output)
        return loaded

    monkeypatch.setattr(orch.loader, "load_contract", _load_contract)
    monkeypatch.setattr(orch.loader, "load", _load)


def test_run_file_pptx_does_not_crash(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(Orchestrator, "_output_root", lambda self: None)
    monkeypatch.delenv("SKILLFORGE_OUTPUT_DIR", raising=False)

    orch = Orchestrator.from_config(llm=_StubLLM())
    monkeypatch.setattr(
        orch.router,
        "route",
        lambda request: RouteDecision(skill="test-skill", confidence=1.0),
    )
    monkeypatch.setattr(orch.gates, "run", lambda *a, **k: _pass_result())
    monkeypatch.setattr(
        orch.queue,
        "generate_all",
        lambda skill, collected: {s: "正文" for s in skill.contract.sections},
    )
    _patched_contract(orch, monkeypatch, "pptx")

    input_json = tmp_path / "input.json"
    input_json.write_text(
        json.dumps({"request": "做 PPT", "collected": {"topic": "示例"}}),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    rc = orch.run_file("test-skill", str(input_json))

    assert rc == 0
    assert (tmp_path / "output.pptx").exists(), "默认应生成 output.pptx"
    assert not (tmp_path / "output.docx").exists(), "不应生成 output.docx"


def test_run_file_docx_default_suffix(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(Orchestrator, "_output_root", lambda self: None)
    monkeypatch.delenv("SKILLFORGE_OUTPUT_DIR", raising=False)

    orch = Orchestrator.from_config(llm=_StubLLM())
    monkeypatch.setattr(
        orch.router,
        "route",
        lambda request: RouteDecision(skill="test-skill", confidence=1.0),
    )
    monkeypatch.setattr(orch.gates, "run", lambda *a, **k: _pass_result())
    monkeypatch.setattr(
        orch.queue,
        "generate_all",
        lambda skill, collected: {s: "正文" for s in skill.contract.sections},
    )
    _patched_contract(orch, monkeypatch, "docx")

    input_json = tmp_path / "input.json"
    input_json.write_text(
        json.dumps({"request": "写开题报告", "collected": {"topic": "示例"}}),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    rc = orch.run_file("test-skill", str(input_json))

    assert rc == 0
    assert (tmp_path / "output.docx").exists()
    assert not (tmp_path / "output.pptx").exists()


def test_run_file_markdown_skips_render(monkeypatch, tmp_path: Path):
    """markdown 技能不传 out_path，只返回草稿，不落盘。"""
    monkeypatch.setattr(Orchestrator, "_output_root", lambda self: None)
    monkeypatch.delenv("SKILLFORGE_OUTPUT_DIR", raising=False)

    orch = Orchestrator.from_config(llm=_StubLLM())
    monkeypatch.setattr(
        orch.router,
        "route",
        lambda request: RouteDecision(skill="test-skill", confidence=1.0),
    )
    monkeypatch.setattr(orch.gates, "run", lambda *a, **k: _pass_result())
    monkeypatch.setattr(
        orch.queue,
        "generate_all",
        lambda skill, collected: {s: "正文" for s in skill.contract.sections},
    )
    _patched_contract(orch, monkeypatch, "markdown")

    input_json = tmp_path / "input.json"
    input_json.write_text(
        json.dumps({"request": "随便", "collected": {"topic": "示例"}}),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    rc = orch.run_file("test-skill", str(input_json))

    assert rc == 0
    assert not (tmp_path / "output.docx").exists()
    assert not (tmp_path / "output.pptx").exists()
