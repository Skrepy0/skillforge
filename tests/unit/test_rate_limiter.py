import pytest

pytest.importorskip("pydantic")

from skillforge.l4_interface.api import FixedWindowRateLimiter


def test_expired_buckets_are_removed(monkeypatch):
    now = 100.0
    monkeypatch.setattr("skillforge.l4_interface.api.time.monotonic", lambda: now)
    limiter = FixedWindowRateLimiter(2, window_seconds=10)
    for key in ["a", "b", "c"]:
        assert limiter.hit(key) == (True, 0)
    assert len(limiter._buckets) == 3
    now = 105.0
    limiter.hit("active")
    now = 110.0
    assert limiter.hit("new") == (True, 0)
    assert set(limiter._buckets) == {"active", "new"}


def test_limit_and_window_reset(monkeypatch):
    now = 100.0
    monkeypatch.setattr("skillforge.l4_interface.api.time.monotonic", lambda: now)
    limiter = FixedWindowRateLimiter(2, window_seconds=10)
    assert limiter.hit("a") == (True, 0)
    assert limiter.hit("a") == (True, 0)
    now = 109.5
    allowed, retry_after = limiter.hit("a")
    assert not allowed
    assert retry_after >= 1
    now = 110.0
    assert limiter.hit("a") == (True, 0)
    assert limiter._buckets["a"] == (110.0, 1)


def test_sweep_is_throttled_even_on_denied_request(monkeypatch):
    now = 100.0
    monkeypatch.setattr("skillforge.l4_interface.api.time.monotonic", lambda: now)
    limiter = FixedWindowRateLimiter(1, window_seconds=10, sweep_interval=20)
    limiter.hit("old")
    now = 115.0
    limiter.hit("active")
    assert "old" in limiter._buckets
    assert limiter._last_sweep == 100.0
    now = 120.0
    allowed, retry_after = limiter.hit("active")
    assert not allowed
    assert retry_after >= 1
    assert set(limiter._buckets) == {"active"}
    assert limiter._last_sweep == 120.0


def test_disabled_limiter_does_not_store_buckets():
    limiter = FixedWindowRateLimiter(0)
    for _ in range(3):
        assert limiter.hit("a") == (True, 0)
    assert not limiter._buckets
