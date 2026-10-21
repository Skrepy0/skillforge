from skillforge.l3_orchestration.session import SessionManager


def test_create_unique_ids():
    mgr = SessionManager()
    a, b = mgr.create("s"), mgr.create("s")
    assert a.session_id != b.session_id
    assert a.skill == "s"


def test_merge_skips_empty_and_strips():
    mgr = SessionManager()
    s = mgr.create("s")
    mgr.merge(s, {"a": "  x  ", "b": "", "c": "   ", "d": "y"})
    assert s.collected == {"a": "x", "d": "y"}


def test_set_drafts_copies():
    mgr = SessionManager()
    s = mgr.create("s")
    src = {"A": "x"}
    mgr.set_drafts(s, src)
    src["A"] = "modified"
    assert s.drafts == {"A": "x"}


def test_bump_rewrite():
    mgr = SessionManager()
    s = mgr.create("s")
    mgr.bump_rewrite(s)
    mgr.bump_rewrite(s)
    assert s.rewrite_rounds == 2


def test_is_ready():
    mgr = SessionManager()
    s = mgr.create("s")
    mgr.merge(s, {"a": "x"})
    assert mgr.is_ready(s, ["a"]) is True
    assert mgr.is_ready(s, ["a", "b"]) is False
