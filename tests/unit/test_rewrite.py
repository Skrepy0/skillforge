from skillforge.l2_capability.loader import LoadedSkill
from skillforge.l2_capability.sanitize import DATA_BEGIN, DATA_END
from skillforge.l3_orchestration.rewrite import Rewriter
from skillforge.shared.types import GateFailure, GateResult, SkillContract


class _Capture:
    def __init__(self, reply="new"):
        self.reply = reply
        self.prompts = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.reply


def _skill():
    return LoadedSkill(
        contract=SkillContract("t", "", ["title"], "markdown", ["A", "B"]),
        instructions="do",
        references={},
    )


def _result(failures):
    return GateResult(passed=False, score=0.5, threshold=0.8, failures=failures)


def test_only_error_sections_rewritten():
    llm = _Capture("new-A")
    out = Rewriter(llm).apply(
        {"A": "old-A", "B": "old-B"},
        _result([GateFailure("r1", "A", "e1", severity="error")]),
        _skill(),
        {},
    )
    assert out == {"A": "new-A", "B": "old-B"}
    assert len(llm.prompts) == 1


def test_warning_only_falls_back_to_first_section():
    llm = _Capture("new-A")
    out = Rewriter(llm).apply(
        {"A": "old-A", "B": "old-B"},
        _result([GateFailure("r1", "A", "e1", severity="warning")]),
        _skill(),
        {},
    )
    assert out == {"A": "new-A", "B": "old-B"}


def test_empty_failures_rewrite_first_section():
    out = Rewriter(_Capture("new-A")).apply(
        {"A": "old-A", "B": "old-B"},
        _result([]),
        _skill(),
        {},
    )
    assert out["A"] == "new-A"
    assert out["B"] == "old-B"


def test_feedback_wrapped_in_boundaries():
    llm = _Capture()
    Rewriter(llm).apply(
        {"A": "old"},
        _result([GateFailure("r1", "A", "evidence-text", severity="error")]),
        _skill(),
        {},
    )
    prompt = llm.prompts[0]
    assert DATA_BEGIN in prompt and DATA_END in prompt
    assert "evidence-text" in prompt


def test_empty_drafts_noop():
    llm = _Capture()
    assert Rewriter(llm).apply({}, _result([]), _skill(), {}) == {}
    assert llm.prompts == []
