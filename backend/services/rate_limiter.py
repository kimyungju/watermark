import time
import threading
from collections import defaultdict


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int | float):
        self._max = max_requests
        self._window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _clean(self, ip: str, now: float) -> None:
        cutoff = now - self._window
        self._requests[ip] = [t for t in self._requests[ip] if t > cutoff]

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        with self._lock:
            self._clean(ip, now)
            if len(self._requests[ip]) >= self._max:
                return False
            self._requests[ip].append(now)
            return True

    def retry_after(self, ip: str) -> int | None:
        now = time.time()
        with self._lock:
            self._clean(ip, now)
            if len(self._requests[ip]) < self._max:
                return None
            oldest = self._requests[ip][0]
            return max(1, int(oldest + self._window - now + 1))
