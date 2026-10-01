import threading
import time

from src.ratelimit import RateLimiter


def test_requests_within_limit_are_allowed():
    limiter = RateLimiter(max_requests=3, window_seconds=60)

    assert limiter.is_allowed("a") is True
    assert limiter.is_allowed("a") is True
    assert limiter.is_allowed("a") is True


def test_request_exceeding_limit_is_rejected():
    limiter = RateLimiter(max_requests=2, window_seconds=60)

    assert limiter.is_allowed("a") is True
    assert limiter.is_allowed("a") is True
    assert limiter.is_allowed("a") is False


def test_different_keys_have_independent_counters():
    limiter = RateLimiter(max_requests=1, window_seconds=60)

    assert limiter.is_allowed("a") is True
    assert limiter.is_allowed("b") is True
    assert limiter.is_allowed("a") is False
    assert limiter.is_allowed("b") is False


def test_counter_resets_after_window_elapses():
    limiter = RateLimiter(max_requests=1, window_seconds=0.05)

    assert limiter.is_allowed("a") is True
    assert limiter.is_allowed("a") is False

    time.sleep(0.1)

    assert limiter.is_allowed("a") is True


def test_concurrent_calls_never_allow_more_than_max_requests():
    limiter = RateLimiter(max_requests=50, window_seconds=60)
    allowed_count = 0
    lock = threading.Lock()

    def hit():
        nonlocal allowed_count
        if limiter.is_allowed("shared-key"):
            with lock:
                allowed_count += 1

    threads = [threading.Thread(target=hit) for _ in range(200)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert allowed_count == 50
