from skillforge.l1_governance.rules.placeholder_check import DEFAULT_MARKERS, check
from skillforge.shared.types import DraftDocument, SessionState, SkillContract

CONTRACT = SkillContract("t", "", [], "markdown", ["正文"])


def _run(body: str, config: dict | None = None):
    draft = DraftDocument("T", [{"heading": "正文", "body": body}])
    return check(draft, CONTRACT, SessionState("s", "t"), config or {})


def test_clean_passes():
    assert _run("完整正文。") == []


def test_default_markers_detected():
    for marker in DEFAULT_MARKERS:
        failures = _run(f"正文 {marker} 结尾")
        assert any(marker in f.evidence for f in failures), marker


def test_custom_markers_override():
    failures = _run("含有 CUSTOM_PLACEHOLDER", {"markers": ["CUSTOM_PLACEHOLDER"]})
    assert len(failures) == 1
    assert failures[0].severity == "error"


def test_override_skips_defaults():
    # 自定义词表不含 TODO，默认词表被替换
    assert _run("TODO", {"markers": ["OTHER"]}) == []
