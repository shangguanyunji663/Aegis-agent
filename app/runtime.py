from __future__ import annotations

import time
from contextlib import contextmanager

from app.config import Settings


class RuntimeServices:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.redis_client = None
        self._locks: dict[str, float] = {}
        self._rate_window: dict[str, list[float]] = {}
        self._redis_available = False
        if settings.redis_url.strip():
            try:
                import redis

                self.redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
                self.redis_client.ping()
                self._redis_available = True
            except Exception:
                self.redis_client = None
                self._redis_available = False

    def redis_status(self) -> str:
        return "up" if self._redis_available else ("configured_but_unavailable" if self.settings.redis_url.strip() else "disabled")

    def check_rate_limit(self, key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        now = time.time()
        if self.redis_client is not None:
            bucket = f"aegis:rate:{key}"
            count = self.redis_client.incr(bucket)
            if count == 1:
                self.redis_client.expire(bucket, window_seconds)
            remaining = max(0, limit - int(count))
            return int(count) <= limit, remaining
        items = [value for value in self._rate_window.get(key, []) if now - value < window_seconds]
        items.append(now)
        self._rate_window[key] = items
        return len(items) <= limit, max(0, limit - len(items))

    @contextmanager
    def lock(self, name: str, ttl_seconds: int):
        acquired = self._acquire_lock(name, ttl_seconds)
        try:
            yield acquired
        finally:
            if acquired:
                self._release_lock(name)

    def _acquire_lock(self, name: str, ttl_seconds: int) -> bool:
        now = time.time()
        if self.redis_client is not None:
            return bool(self.redis_client.set(f"aegis:lock:{name}", str(now), nx=True, ex=ttl_seconds))
        expires_at = self._locks.get(name, 0.0)
        if expires_at > now:
            return False
        self._locks[name] = now + ttl_seconds
        return True

    def _release_lock(self, name: str) -> None:
        if self.redis_client is not None:
            self.redis_client.delete(f"aegis:lock:{name}")
        self._locks.pop(name, None)
