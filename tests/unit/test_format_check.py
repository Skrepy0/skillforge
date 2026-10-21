"""format_check 单元测试：章节缺失、顺序错、字数区间、目标值优先级。"""

from skillforge.l1_governance.rules.format_check import check
from skillforge.shared.types import DraftDocument, SessionState, SkillContract

CONTRACT = SkillContract(
    name="t",
    description="",
    required_fields=[],
    output="markdown",
    sections=["背景", "方法", "结论"],
)
CONFIG = {"enabled": True, "weight": 0.5, "default_word_count": 300, "tolerance": 0.1}


def _draft(*pairs: tuple[str, str]) -> DraftDocument:
    return DraftDocument("标题", [{"heading": h, "body": b} for h, b in pairs])


def _session(**collected: str) -> SessionState:
    return SessionState("s1", "t", collected=dict(collected))


def _body(n: int) -> str:
    return "字" * n


# ---------- 章节结构 ----------


def test_complete_and_in_order_passes():
    draft = _draft(("背景", _body(100)), ("方法", _body(100)), ("结论", _body(100)))
    assert check(draft, CONTRACT, _session(), CONFIG) == []


def test_missing_sections_reported_individually():
    # 只给“结论”一章，缺“背景”“方法”，字数 300 在区间内
    draft = _draft(("结论", _body(300)))
    failures = check(draft, CONTRACT, _session(), CONFIG)
    assert len(failures) == 2
    assert {f.section for f in failures} == {"背景", "方法"}
    assert all("缺少必需章节" in f.evidence for f in failures)


def test_missing_section_does_not_also_report_order():
    # 缺“背景”且顺序也不对，应只报缺失，不重复报顺序
    draft = _draft(("结论", _body(150)), ("方法", _body(150)))
    failures = check(draft, CONTRACT, _session(), CONFIG)
    assert len(failures) == 1
    assert "缺少" in failures[0].evidence
    assert all("顺序" not in f.evidence for f in failures)


def test_wrong_order_reports_once():
    draft = _draft(("方法", _body(100)), ("背景", _body(100)), ("结论", _body(100)))
    failures = check(draft, CONTRACT, _session(), CONFIG)
    assert len(failures) == 1
    assert "顺序" in failures[0].evidence
    assert failures[0].section == "（全文）"


# ---------- 字数区间 ----------


def test_word_count_too_short():
    draft = _draft(("背景", _body(10)), ("方法", _body(10)), ("结论", _body(10)))
    failures = check(draft, CONTRACT, _session(), CONFIG)
    assert len(failures) == 1
    assert "总字数 30" in failures[0].evidence
    assert "[270, 330]" in failures[0].evidence


def test_word_count_too_long():
    draft = _draft(("背景", _body(200)), ("方法", _body(200)), ("结论", _body(200)))
    failures = check(draft, CONTRACT, _session(), CONFIG)
    assert len(failures) == 1
    assert "总字数 600" in failures[0].evidence


def test_word_count_boundary_inclusive():
    # 恰好 270 与 330 都应在区间内
    for total in (270, 330):
        per = total // 3
        draft = _draft(("背景", _body(per)), ("方法", _body(per)), ("结论", _body(total - per * 2)))
        failures = check(draft, CONTRACT, _session(), CONFIG)
        assert not any("总字数" in f.evidence for f in failures), f"total={total}"


def test_word_count_ignores_whitespace():
    body = ("字" * 50 + "\n  ") * 2  # 100 个非空白字符，带换行与空格
    draft = _draft(("背景", body), ("方法", _body(100)), ("结论", _body(100)))
    failures = check(draft, CONTRACT, _session(), CONFIG)
    assert not any("总字数" in f.evidence for f in failures)


# ---------- 目标值优先级 ----------


def test_user_target_overrides_config():
    # 配置默认 300，用户要求 100；草稿 300 字，只有用户值生效才会失败
    draft = _draft(("背景", _body(100)), ("方法", _body(100)), ("结论", _body(100)))
    failures = check(draft, CONTRACT, _session(target_word_count="100"), CONFIG)
    assert any("总字数 300" in f.evidence for f in failures)


def test_invalid_target_falls_back_to_config():
    # 用户值无法转 int → 回退配置 300；300 字应通过
    draft = _draft(("背景", _body(100)), ("方法", _body(100)), ("结论", _body(100)))
    failures = check(draft, CONTRACT, _session(target_word_count="一千八"), CONFIG)
    assert failures == []


def test_invalid_tolerance_falls_back_to_default():
    # tolerance 配成字符串 → 回退 0.1，区间仍是 [270, 330]
    bad_config = {**CONFIG, "tolerance": "abc"}
    draft = _draft(("背景", _body(100)), ("方法", _body(100)), ("结论", _body(100)))
    failures = check(draft, CONTRACT, _session(), bad_config)
    assert failures == []
