import redis
from app.config import settings


def get_redis_client() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def check_cost_limit() -> tuple[bool, dict]:
    try:
        r = get_redis_client()
    except Exception:
        return True, {"error": "Redis unavailable, cost check skipped"}

    month_key = "cost:current_month"
    total_spent = float(r.get(month_key) or "0.0")

    if total_spent >= settings.COST_LIMIT_USD:
        return False, {
            "total_spent": total_spent,
            "limit": settings.COST_LIMIT_USD,
            "message": "Monthly cost limit exceeded.",
        }

    return True, {
        "total_spent": total_spent,
        "limit": settings.COST_LIMIT_USD,
        "remaining": settings.COST_LIMIT_USD - total_spent,
    }


def record_request_cost() -> float:
    try:
        r = get_redis_client()
    except Exception:
        return 0.0

    month_key = "cost:current_month"
    r.incrbyfloat(month_key, settings.COST_PER_REQUEST)
    r.expire(month_key, 86400 * 31)

    return float(r.get(month_key) or "0.0")
