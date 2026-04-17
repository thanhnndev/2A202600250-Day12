from fastapi import Request, HTTPException, status
from app.config import settings


async def verify_api_key(request: Request) -> None:
    api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization")

    if api_key and api_key.startswith("Bearer "):
        api_key = api_key[7:]

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide via X-API-Key header.",
        )

    if api_key != settings.AGENT_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key."
        )
