import json
from typing import Any, Protocol

from app.core.config import get_cache_settings


class JsonCache(Protocol):
    async def get_json(self, key: str) -> Any | None:
        ...

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        ...


class NullJsonCache:
    async def get_json(self, key: str) -> None:
        return None

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        return None


class ValkeyJsonCache:
    def __init__(self, url: str) -> None:
        from redis import asyncio as redis

        self._client = redis.from_url(url, decode_responses=True)

    async def get_json(self, key: str) -> Any | None:
        try:
            cached = await self._client.get(key)
        except Exception:
            return None
        if cached is None:
            return None
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            return None

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        try:
            await self._client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
        except Exception:
            return None


_default_cache: JsonCache | None = None


def get_default_cache() -> JsonCache:
    global _default_cache
    if _default_cache is not None:
        return _default_cache

    settings = get_cache_settings()
    if not settings.valkey_url:
        _default_cache = NullJsonCache()
    else:
        _default_cache = ValkeyJsonCache(settings.valkey_url)
    return _default_cache
