import time
import redis
from fastapi import Request, HTTPException, status
from app.config import settings


def get_redis_client() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


async def check_rate_limit(request: Request) -> None:
    try:
        r = get_redis_client()
    except Exception:
        return

    api_key = request.headers.get("X-API-Key", "unknown")
    key = f"ratelimit:{api_key}"

    now = time.time()
    window_start = now - settings.RATE_LIMIT_WINDOW

    r.zremrangebyscore(key, 0, window_start)

    current_count = r.zcard(key)

    if current_count >= settings.RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Max {settings.RATE_LIMIT_REQUESTS} requests per {settings.RATE_LIMIT_WINDOW}s.",
        )

    r.zadd(key, {f"{now}:{id(request)}": now})
    r.expire(key, settings.RATE_LIMIT_WINDOW + 10)
