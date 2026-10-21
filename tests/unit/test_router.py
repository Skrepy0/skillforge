from skillforge.l3_orchestration.router import Router
from skillforge.shared.config import RoutingConfig


def _config(keywords=None, threshold=0.5, gap=0.1):
    return RoutingConfig(
        similarity_threshold=threshold,
        clarify_gap=gap,
        keywords=keywords or {"skill-a": ["alpha"], "skill-b": ["beta"]},
    )


def test_no_hit_returns_clarification():
    d = Router(_config()).route("完全无关")
    assert d.skill is None
    assert d.needs_clarification is True


def test_hit_below_threshold_returns_clarification():
    cfg = _config(keywords={"skill-a": ["alpha", "beta", "gamma", "delta"]})
    d = Router(cfg).route("alpha")
    assert d.skill is None
    assert d.needs_clarification is True


def test_normal_hit_returns_top_skill():
    d = Router(_config(keywords={"skill-a": ["alpha"]})).route("alpha")
    assert d.skill == "skill-a"
    assert d.confidence == 1.0
    assert d.needs_clarification is False


def test_candidates_sorted_descending():
    cfg = _config(
        keywords={"skill-a": ["alpha", "beta"], "skill-b": ["alpha", "gamma"]},
        threshold=0.3,
        gap=0.01,
    )
    d = Router(cfg).route("alpha beta")
    assert d.skill == "skill-a"
    scores = [s for _, s in d.candidates]
    assert scores == sorted(scores, reverse=True)


def test_ambiguous_top_two_triggers_clarification():
    cfg = _config(
        keywords={"skill-a": ["alpha", "beta"], "skill-b": ["alpha", "gamma"]},
        threshold=0.3,
        gap=0.5,
    )
    d = Router(cfg).route("alpha")
    assert d.skill is None
    assert d.needs_clarification is True
