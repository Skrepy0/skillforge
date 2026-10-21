from skillforge.l1_governance.rules.repetition_check import check
from skillforge.shared.types import DraftDocument, SessionState, SkillContract

CONTRACT = SkillContract("t", "", [], "markdown", ["正文"])
CONFIG = {"enabled": True, "weight": 0.15, "max_repeat": 2, "max_ratio": 0.3}


def _run(body: str):
    draft = DraftDocument("T", [{"heading": "正文", "body": body}])
    return check(draft, CONTRACT, SessionState("s", "t"), CONFIG)


def test_clean_passes():
    assert _run("第一行。\n第二行。\n第三行。") == []


def test_line_over_repeat_is_warning():
    body = "重复行。\n重复行。\n重复行。\n另一行。"
    failures = _run(body)
    warnings = [f for f in failures if f.severity == "warning"]
    assert any("重复 3 次" in f.evidence for f in warnings)


def test_high_ratio_is_error():
    body = "重复。\n重复。\n重复。\n重复。\n唯一。"
    failures = _run(body)
    errors = [f for f in failures if f.severity == "error"]
    assert any("重复率" in f.evidence for f in errors)


def test_config_override_relaxes_thresholds():
    body = "重复。\n重复。\n重复。\n唯一1。\n唯一2。\n唯一3。"
    draft = DraftDocument("T", [{"heading": "正文", "body": body}])

    # 默认 max_repeat=2：单行重复 3 次触发 warning
    default_failures = check(draft, CONTRACT, SessionState("s", "t"), CONFIG)
    assert any(f.severity == "warning" for f in default_failures)

    # 覆盖 max_repeat=5 后：无 warning，重复率 0.5 ≤ 0.9，无 error
    override = {**CONFIG, "max_repeat": 5, "max_ratio": 0.9}
    assert check(draft, CONTRACT, SessionState("s", "t"), override) == []
