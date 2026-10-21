"""format_check 与 cliche_check 在 GateRunner 中的协同。"""

from skillforge.l1_governance.gate_runner import GateRunner
from skillforge.shared.config import GatesConfig
from skillforge.shared.types import DraftDocument, SessionState, SkillContract

CONTRACT = SkillContract(
    name="t",
    description="",
    required_fields=[],
    output="markdown",
    sections=["背景", "方法", "结论"],
)

GATES = GatesConfig(
    pass_threshold=0.85,
    rules={
        "cliche_check": {"enabled": True, "weight": 0.5, "phrases": ["名列前茅"]},
        "format_check": {
            "enabled": True,
            "weight": 0.5,
            "default_word_count": 300,
            "tolerance": 0.1,
        },
    },
)


def _draft(*pairs: tuple[str, str]) -> DraftDocument:
    return DraftDocument("标题", [{"heading": h, "body": b} for h, b in pairs])


def _run(*pairs: tuple[str, str]):
    session = SessionState("s1", "t")
    return GateRunner(GATES).run(_draft(*pairs), CONTRACT, session, trace_id="t1")


def test_clean_draft_passes_with_full_score():
    result = _run(("背景", "字" * 100), ("方法", "字" * 100), ("结论", "字" * 100))
    assert result.passed is True
    assert result.score == 1.0
    assert result.failures == []


def test_single_cliche_tolerated():
    # cliche 0.8 + format 1.0 → 加权 0.9 ≥ 0.85，仍通过
    result = _run(("背景", "名列前茅。" + "字" * 95), ("方法", "字" * 100), ("结论", "字" * 100))
    assert result.passed is True
    assert result.score == 0.9
    assert {f.rule for f in result.failures} == {"cliche_check"}


def test_cliche_and_word_count_both_fail():
    # cliche 0.8 + format 0.8 → 加权 0.8 < 0.85，不通过
    result = _run(("背景", "名列前茅。" + "字" * 5), ("方法", "字" * 10), ("结论", "字" * 10))
    assert result.passed is False
    assert result.score == 0.8
    assert {f.rule for f in result.failures} == {"cliche_check", "format_check"}


def test_disabled_rule_not_counted():
    # 关闭 cliche_check 后，套话不再影响得分
    gates = GatesConfig(
        pass_threshold=0.85,
        rules={
            "cliche_check": {"enabled": False, "weight": 0.5, "phrases": ["名列前茅"]},
            "format_check": {
                "enabled": True,
                "weight": 0.5,
                "default_word_count": 300,
                "tolerance": 0.1,
            },
        },
    )
    session = SessionState("s1", "t")
    draft = _draft(("背景", "名列前茅。" + "字" * 95), ("方法", "字" * 100), ("结论", "字" * 100))
    result = GateRunner(gates).run(draft, CONTRACT, session, trace_id="t1")
    assert result.passed is True
    assert result.score == 1.0
    assert result.failures == []
