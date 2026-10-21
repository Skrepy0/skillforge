from skillforge.l3_orchestration.orchestrator import Orchestrator


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


def _always_pass():
    from skillforge.shared.types import GateResult

    return GateResult(passed=True, score=1.0, threshold=0.8, failures=[])
