from skillforge.l1_governance.rules.sensitive_check import DEFAULT_WORDS, check
from skillforge.shared.types import DraftDocument, SessionState, SkillContract

CONTRACT = SkillContract("t", "", [], "markdown", ["正文"])


def _run(body: str, config: dict):
    draft = DraftDocument("T", [{"heading": "正文", "body": body}])
    return check(draft, CONTRACT, SessionState("s", "t"), config)


def test_empty_wordlist_passes():
    assert _run("任何内容", {"enabled": True}) == []
    assert DEFAULT_WORDS == ()


def test_hit_returns_error():
    failures = _run("包含违禁词", {"enabled": True, "words": ["违禁词"]})
    assert len(failures) == 1
    assert failures[0].severity == "error"
    assert "违禁词" in failures[0].evidence


def test_same_word_once_per_section():
    failures = _run("违禁词违禁词违禁词", {"enabled": True, "words": ["违禁词"]})
    assert len(failures) == 1


def test_severity_override():
    failures = _run("违禁词", {"enabled": True, "words": ["违禁词"], "severity": "warning"})
    assert failures[0].severity == "warning"


def test_words_stripped_and_empty_filtered():
    failures = _run("违禁词", {"enabled": True, "words": [" 违禁词 ", ""]})
    assert len(failures) == 1
