import time
from services.rate_limiter import RateLimiter

def test_allows_requests_under_limit():
    limiter = RateLimiter(max_requests=5, window_seconds=60)
    for _ in range(5):
        assert limiter.is_allowed("127.0.0.1") is True

def test_blocks_requests_over_limit():
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    assert limiter.is_allowed("1.1.1.1") is True
    assert limiter.is_allowed("1.1.1.1") is True
    assert limiter.is_allowed("1.1.1.1") is False

def test_different_ips_tracked_separately():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.is_allowed("1.1.1.1") is True
    assert limiter.is_allowed("2.2.2.2") is True
    assert limiter.is_allowed("1.1.1.1") is False

def test_window_expires():
    limiter = RateLimiter(max_requests=1, window_seconds=0.1)
    assert limiter.is_allowed("1.1.1.1") is True
    assert limiter.is_allowed("1.1.1.1") is False
    time.sleep(0.15)
    assert limiter.is_allowed("1.1.1.1") is True

def test_retry_after_returns_seconds():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter.is_allowed("1.1.1.1")
    limiter.is_allowed("1.1.1.1")
    retry = limiter.retry_after("1.1.1.1")
    assert retry is not None
    assert 0 < retry <= 60
