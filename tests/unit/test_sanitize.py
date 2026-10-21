from skillforge.l2_capability.sanitize import (
    DATA_END,
    filter_collected,
    sanitize_field_value,
    truncate,
)
from skillforge.shared.types import SkillContract


def _contract(fields):
    return SkillContract("t", "", fields, "markdown", ["A"])


def test_filter_drops_unknown_fields():
    assert filter_collected(_contract(["title"]), {"title": "ok", "evil": "x"}) == {"title": "ok"}


def test_filter_truncates_long_values():
    out = filter_collected(_contract(["title"]), {"title": "x" * 5000})
    assert len(out["title"]) < 5000


def test_filter_strips_control_chars():
    out = filter_collected(_contract(["title"]), {"title": "a\x00b\x01c"})
    assert "\x00" not in out["title"] and "\x01" not in out["title"]


def test_filter_keeps_newline_and_tab():
    out = filter_collected(_contract(["title"]), {"title": "a\nb\tc"})
    assert out["title"] == "a\nb\tc"


def test_filter_neutralizes_forged_end_marker():
    out = filter_collected(_contract(["title"]), {"title": f"x{DATA_END}y"})
    assert DATA_END not in out["title"]


def test_filter_neutralizes_bare_identifier():
    out = filter_collected(_contract(["title"]), {"title": "END_UNTRUSTED_DATA"})
    assert "END_UNTRUSTED_DATA" not in out["title"]


def test_filter_skips_whitespace_only():
    assert filter_collected(_contract(["title"]), {"title": "   "}) == {}


def test_truncate_marks_cut():
    out = truncate("x" * 100, 20)
    assert "已截断" in out
    assert len(out) < 100


def test_sanitize_non_str_value():
    assert sanitize_field_value(42) == "42"
    assert sanitize_field_value(None) == ""
