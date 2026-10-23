import pytest
from skillforge.l2_capability.loader import LoadedSkill
from skillforge.l3_orchestration.task_queue import TaskQueue
from skillforge.shared.types import SkillContract


class _Plain:
    def __init__(self):
        self.calls = []

    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        return "plain"


class _System:
    def __init__(self):
        self.calls = []

    def complete(self, prompt: str) -> str:
        raise AssertionError("不应调用 complete")

    def complete_system(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return "system"


def _skill(sections=None) -> LoadedSkill:
    return LoadedSkill(
        contract=SkillContract("t", "", ["title"], "markdown", sections or ["A", "B"]),
        instructions="do",
        references={},
    )


def test_plain_llm_path():
    llm = _Plain()
    out = TaskQueue(llm, concurrency=1).generate_all(_skill(), {"title": "x"})
    assert out == {"A": "plain", "B": "plain"}
    assert len(llm.calls) == 2


def test_system_llm_path():
    llm = _System()
    out = TaskQueue(llm, concurrency=1).generate_all(_skill(), {"title": "x"})
    assert out == {"A": "system", "B": "system"}
    for system, user in llm.calls:
        assert "安全规则" in system
        assert "已采集信息" in user


@pytest.mark.parametrize("bad", [0, -5])
def test_concurrency_clamped_to_one(bad):
    assert TaskQueue(_Plain(), concurrency=bad).concurrency == 1


def test_generate_all_returns_all_sections():
    out = TaskQueue(_Plain(), concurrency=2).generate_all(_skill(["A", "B", "C"]), {})
    assert set(out) == {"A", "B", "C"}


@pytest.mark.parametrize("system", [False, True])
def test_client_failure_normalized(system):
    from skillforge.shared.errors import LLMError

    class Broken:
        def complete(self, prompt):
            raise RuntimeError("provider failed")

    class BrokenSystem(Broken):
        def complete_system(self, system, user):
            raise RuntimeError("provider failed")

    with pytest.raises(LLMError) as caught:
        TaskQueue(BrokenSystem() if system else Broken()).generate_all(_skill(), {})
    assert isinstance(caught.value.__cause__, RuntimeError)


def test_classified_error_preserved():
    from skillforge.shared.errors import LLMError

    exc = LLMError("failed")

    class Broken:
        def complete(self, prompt):
            raise exc

    with pytest.raises(LLMError) as caught:
        TaskQueue(Broken()).generate_all(_skill(), {})
    assert caught.value is exc


def test_pptx_four_short_points_fit_three_slots_without_losing_facts():
    from skillforge.l2_capability.pptx_content import slide_blocks, slide_content_errors

    class FourPoints(_Plain):
        def complete(self, prompt):
            self.calls.append(prompt)
            return "单比特穷举8种\n8位总线共131072种\n逐项比较预期输出\n实际仿真待执行"

    skill = LoadedSkill(SkillContract("ppt", "", [], "pptx", ["步骤四"]), "", {})
    llm = FourPoints()
    body = TaskQueue(llm).generate_all(skill, {})["步骤四"]
    assert len(slide_blocks(body)) == 3
    for fact in ("单比特穷举8种", "8位总线共131072种", "逐项比较预期输出", "实际仿真待执行"):
        assert fact in body
    assert not slide_content_errors(body, "步骤四")
    assert len(llm.calls) == 1


def test_pptx_retry_includes_previous_draft_and_concrete_repair_request():
    bad = "\n".join(["甲" * 80, "乙" * 80, "丙" * 80, "丁" * 80])

    class Repair(_Plain):
        def complete(self, prompt):
            self.calls.append(prompt)
            if len(self.calls) == 1:
                return bad
            assert bad in prompt
            assert "最多3行" in prompt
            return "单比特覆盖8种\n8位覆盖131072种\n仿真结果待确认"

    skill = LoadedSkill(SkillContract("ppt", "", [], "pptx", ["步骤四"]), "", {})
    llm = Repair()
    assert "131072" in TaskQueue(llm).generate_all(skill, {})["步骤四"]
    assert len(llm.calls) == 2


def test_pptx_unfit_points_still_fail_instead_of_dropping_content():
    from skillforge.shared.errors import LLMError

    class Unfit(_Plain):
        def complete(self, prompt):
            self.calls.append(prompt)
            return "\n".join(["甲" * 80, "乙" * 80, "丙" * 80, "丁" * 80])

    skill = LoadedSkill(SkillContract("ppt", "", [], "pptx", ["步骤四"]), "", {})
    llm = Unfit()
    with pytest.raises(LLMError, match="实际4条"):
        TaskQueue(llm).generate_all(skill, {})
    assert len(llm.calls) == 3


def test_complex_input_verification_prompt_does_not_force_single_bit_coverage():
    import json
    from pathlib import Path

    from skillforge.l2_capability.loader import Loader
    from skillforge.l2_capability.prompt_builder import build_user_prompt

    root = Path(__file__).resolve().parents[2]
    skill = Loader(root / "skills").load("hnu-digital-circuit-seminar-ppt")
    collected = json.loads((root / "examples/ppt-request-complex.json").read_text("utf-8"))[
        "collected"
    ]
    prompt = build_user_prompt(skill, "步骤四", collected)
    assert "131072" in prompt
    assert "遍历三输入的8种组合" not in prompt
    assert "三输入如何覆盖8种组合" not in prompt
    assert "以已采集信息为准" in prompt
