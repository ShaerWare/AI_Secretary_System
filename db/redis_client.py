"""
Redis client for caching and realtime data.

Features:
- Session caching with TTL
- Rate limiting
- Realtime metrics
- Pub/sub for events

Note: Redis is optional. If not available, operations gracefully fail.
"""

import json
import logging
import os
from typing import Any, Optional


logger = logging.getLogger(__name__)

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_AVAILABLE = False

# Try to import redis
try:
    import redis.asyncio as redis

    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    logger.warning("⚠️ Redis not available (redis package not installed)")

# Global redis client
redis_client: Optional["redis.Redis"] = None


async def init_redis() -> bool:
    """
    Initialize Redis connection.
    Returns True if successful, False otherwise.
    """
    global redis_client, REDIS_AVAILABLE

    if not REDIS_AVAILABLE:
        return False

    try:
        redis_client = redis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        # Test connection
        await redis_client.ping()
        logger.info(f"🔴 Redis connected at {REDIS_URL}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Redis not available: {e}")
        redis_client = None
        REDIS_AVAILABLE = False
        return False


async def close_redis():
    """Close Redis connection."""
    global redis_client
    if redis_client:
        await redis_client.close()
        logger.info("🔴 Redis connection closed")
        redis_client = None


async def get_redis() -> Optional["redis.Redis"]:
    """Get Redis client instance."""
    return redis_client


async def get_redis_status() -> dict:
    """Get Redis connection status for health checks."""
    if not redis_client:
        return {"status": "unavailable", "error": "Not connected"}

    try:
        info = await redis_client.info("server")
        memory = await redis_client.info("memory")
        return {
            "status": "ok",
            "version": info.get("redis_version"),
            "used_memory_mb": round(memory.get("used_memory", 0) / (1024 * 1024), 2),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ============== Cache Helpers ==============


class CacheKey:
    """Cache key prefixes"""

    SESSION = "session"
    CHAT_SESSION = "chat:session"
    FAQ = "faq:cache"
    METRICS = "metrics"
    RATE_LIMIT = "ratelimit"
    TTS_PRESET = "tts:preset"
    CONFIG = "config"


async def cache_get(key: str) -> Optional[Any]:
    """Get value from cache, returns None if not found or Redis unavailable."""
    if not redis_client:
        return None
    try:
        value = await redis_client.get(key)
        if value:
            return json.loads(value)
        return None
    except Exception as e:
        logger.debug(f"Cache get error for {key}: {e}")
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> bool:
    """Set value in cache with TTL. Returns True if successful."""
    if not redis_client:
        return False
    try:
        await redis_client.setex(
            key,
            ttl_seconds,
            json.dumps(value, ensure_ascii=False),
        )
        return True
    except Exception as e:
        logger.debug(f"Cache set error for {key}: {e}")
        return False


async def cache_delete(key: str) -> bool:
    """Delete value from cache. Returns True if successful."""
    if not redis_client:
        return False
    try:
        await redis_client.delete(key)
        return True
    except Exception as e:
        logger.debug(f"Cache delete error for {key}: {e}")
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """Delete all keys matching pattern. Returns number of deleted keys."""
    if not redis_client:
        return 0
    try:
        keys = await redis_client.keys(pattern)
        if keys:
            return await redis_client.delete(*keys)
        return 0
    except Exception as e:
        logger.debug(f"Cache delete pattern error for {pattern}: {e}")
        return 0


# ============== Rate Limiting ==============


async def check_rate_limit(
    key: str,
    max_requests: int = 60,
    window_seconds: int = 60,
) -> tuple[bool, int]:
    """
    Check if rate limit is exceeded.
    Returns (allowed: bool, remaining: int).
    """
    if not redis_client:
        return True, max_requests  # Allow all if Redis unavailable

    try:
        current = await redis_client.incr(key)
        if current == 1:
            await redis_client.expire(key, window_seconds)

        remaining = max(0, max_requests - current)
        return current <= max_requests, remaining
    except Exception as e:
        logger.debug(f"Rate limit check error: {e}")
        return True, max_requests


async def get_rate_limit_key(ip: str, endpoint: str) -> str:
    """Generate rate limit key for IP and endpoint."""
    return f"{CacheKey.RATE_LIMIT}:{ip}:{endpoint}"


# ============== Session Management ==============


async def cache_session(session_id: str, data: dict, ttl_seconds: int = 300) -> bool:
    """Cache chat session data."""
    key = f"{CacheKey.CHAT_SESSION}:{session_id}"
    return await cache_set(key, data, ttl_seconds)


async def get_cached_session(session_id: str) -> Optional[dict]:
    """Get cached chat session data."""
    key = f"{CacheKey.CHAT_SESSION}:{session_id}"
    return await cache_get(key)


async def invalidate_session_cache(session_id: str) -> bool:
    """Invalidate chat session cache."""
    key = f"{CacheKey.CHAT_SESSION}:{session_id}"
    return await cache_delete(key)


# ============== FAQ Cache ==============


async def cache_faq(data: dict, ttl_seconds: int = 600) -> bool:
    """Cache FAQ data."""
    return await cache_set(CacheKey.FAQ, data, ttl_seconds)


async def get_cached_faq() -> Optional[dict]:
    """Get cached FAQ data."""
    return await cache_get(CacheKey.FAQ)


async def invalidate_faq_cache() -> bool:
    """Invalidate FAQ cache."""
    return await cache_delete(CacheKey.FAQ)


# ============== Metrics ==============


async def set_metric(name: str, value: Any, ttl_seconds: int = 10) -> bool:
    """Set a realtime metric."""
    key = f"{CacheKey.METRICS}:{name}"
    return await cache_set(key, value, ttl_seconds)


async def get_metric(name: str) -> Optional[Any]:
    """Get a realtime metric."""
    key = f"{CacheKey.METRICS}:{name}"
    return await cache_get(key)


# ============== Config Cache ==============


async def cache_config(config_key: str, data: dict, ttl_seconds: int = 300) -> bool:
    """Cache system config."""
    key = f"{CacheKey.CONFIG}:{config_key}"
    return await cache_set(key, data, ttl_seconds)


async def get_cached_config(config_key: str) -> Optional[dict]:
    """Get cached system config."""
    key = f"{CacheKey.CONFIG}:{config_key}"
    return await cache_get(key)


async def invalidate_config_cache(config_key: str) -> bool:
    """Invalidate config cache."""
    key = f"{CacheKey.CONFIG}:{config_key}"
    return await cache_delete(key)
