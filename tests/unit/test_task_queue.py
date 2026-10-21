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
