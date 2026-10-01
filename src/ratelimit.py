"""A small, thread-safe, in-memory rate limiter.

Used by both the Discourse webhook route (src/api/webhooks.py, keyed by
source IP) and the Slack command middleware (src/integrations/slack.py,
keyed by Slack user ID) — see the add-rate-limiting design.md for why a
single process-local, lock-guarded fixed-window counter is sufficient for
this single-process deployment (no Redis or other shared store).

Fixed window, not sliding: simpler, and the known imprecision (up to
roughly 2x the configured rate across a window boundary) is an acceptable
trade-off for abuse mitigation rather than a hard security boundary.
"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """Allows up to `max_requests` calls to is_allowed() per key, per window_seconds."""

    def __init__(self, *, max_requests: int, window_seconds: int) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._lock = threading.Lock()
        self._counters: dict[str, tuple[float, int]] = {}

    def is_allowed(self, key: str) -> bool:
        """Return True if `key` has not yet exceeded the limit for the current window.

        Counts this call toward the limit regardless of the outcome, so
        the caller should treat a False return as "this attempt is
        rejected" rather than retry is_allowed() again for the same
        attempt.
        """
        now = time.monotonic()
        with self._lock:
            window_start, count = self._counters.get(key, (now, 0))
            if now - window_start >= self._window_seconds:
                window_start, count = now, 0
            count += 1
            self._counters[key] = (window_start, count)
            return count <= self._max_requests
