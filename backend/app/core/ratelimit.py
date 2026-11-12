"""Tiny in-memory sliding-window limiter. Protects the Gemini quota and CPU. Per process, resets on restart."""
import time
from collections import defaultdict, deque


class SlidingWindow:
    def __init__(self, limit: int, window_seconds: float = 60.0):
        self.limit, self.window = limit, window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        if self.limit <= 0:
            return True
        now = time.monotonic() if now is None else now
        q = self._hits[key]
        while q and now - q[0] >= self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        if len(self._hits) > 5000:  # keep memory bounded
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
                self._hits.pop(k, None)
        return True
