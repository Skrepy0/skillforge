from pathlib import Path

from skillforge.l3_orchestration.orchestrator import Orchestrator
from skillforge.shared.types import GateResult


class _CapturingLLM:
    def __init__(self):
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "章节正文"


def test_orchestrator_drops_unknown_collected(monkeypatch):
    from skillforge.shared.types import RouteDecision

    llm = _CapturingLLM()
    orch = Orchestrator.from_config(llm=llm)

    monkeypatch.setattr(
        orch.router,
        "route",
        lambda request: RouteDecision(skill="test-skill", confidence=1.0),
    )
    monkeypatch.setattr(orch.gates, "run", lambda *a, **k: _always_pass())
    monkeypatch.setattr(orch.renderer, "render", lambda draft, out: out)

    contract = orch.loader.load_contract("test-skill")
    fields = list(contract.required_fields)
    assert fields, "test-skill 必须至少声明一个 required_field"

    # 所有契约内字段都填上；把第一个字段设成可断言的值
    collected = {f: f"value-{f}" for f in fields}
    collected[fields[0]] = "合法题目"
    collected["evil_field"] = "SECRET_LEAK_MARKER"  # 契约外，应被丢弃

    result = orch.run(
        request="帮我写开题报告",
        collected=collected,
        out_path=None,
    )
    assert result["status"] == "delivered", result
    joined = "\n".join(llm.prompts)
    assert "SECRET_LEAK_MARKER" not in joined
    assert "合法题目" in joined


def _always_pass() -> GateResult:
    from skillforge.shared.types import GateResult

    return GateResult(passed=True, score=1.0, threshold=0.8)


def test_orchestrator_pptx_output_dispatches_to_pptx_renderer(monkeypatch, tmp_path):
    from skillforge.l3_orchestration.orchestrator import Orchestrator
    from skillforge.shared.types import RouteDecision

    # 本测试只关心渲染器分派，路径白名单由 test_loader_path / test_api_out_path 覆盖
    monkeypatch.setattr(Orchestrator, "_output_root", lambda self: None)
    monkeypatch.delenv("SKILLFORGE_OUTPUT_DIR", raising=False)

    calls = {"docx": 0, "pptx": 0}

    class _SpyDocx:
        def render(self, draft, out_path):
            calls["docx"] += 1
            return Path(out_path)

    class _SpyPptx:
        def render(self, draft, out_path):
            calls["pptx"] += 1
            return Path(out_path)

    llm = _CapturingLLM()
    orch = Orchestrator.from_config(llm=llm)
    orch.renderer = _SpyDocx()
    orch.pptx_renderer = _SpyPptx()

    monkeypatch.setattr(
        orch.router,
        "route",
        lambda request: RouteDecision(skill="test-skill", confidence=1.0),
    )
    monkeypatch.setattr(orch.gates, "run", lambda *a, **k: _always_pass())
    monkeypatch.setattr(
        orch.queue,
        "generate_all",
        lambda skill, collected: {s: "正文" for s in skill.contract.sections},
    )

    real_load = orch.loader.load

    def _patched_load(name):
        loaded = real_load(name)
        object.__setattr__(loaded.contract, "output", "pptx")
        return loaded

    monkeypatch.setattr(orch.loader, "load", _patched_load)

    contract = orch.loader.load_contract("test-skill")
    collected = {f: f"v-{f}" for f in contract.required_fields}
    result = orch.run(
        request="x",
        collected=collected,
        out_path=tmp_path / "x.pptx",
    )
    assert result["status"] == "delivered"
    assert calls["pptx"] == 1
    assert calls["docx"] == 0
