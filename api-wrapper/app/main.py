"""
API Gateway Wrapper for FindMyPath Agents.

Provides:
- API Key authentication
- Rate limiting (Redis-backed)
- Cost guard ($10/month limit)
- Health + readiness checks
- Graceful shutdown
- Request logging

Port: 18001
"""

import signal
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.auth import verify_api_key
from app.rate_limiter import check_rate_limit
from app.cost_guard import check_cost_limit, record_request_cost

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

shutdown_event = asyncio.Event()


class AskRequest(BaseModel):
    user_id: str = Field(..., description="User identifier")
    question: str = Field(..., description="User question")
    session_id: str | None = Field(None, description="Session ID for continuity")


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str


class ReadinessResponse(BaseModel):
    status: str
    redis: str
    backend: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting API Wrapper v{settings.APP_VERSION} on port {settings.PORT}")
    logger.info(f"Backend URL: {settings.BACKEND_URL}")
    logger.info(
        f"Rate limit: {settings.RATE_LIMIT_REQUESTS} req/{settings.RATE_LIMIT_WINDOW}s"
    )
    logger.info(f"Cost limit: ${settings.COST_LIMIT_USD}/month")
    yield
    logger.info("Shutting down API Wrapper...")
    shutdown_event.set()


app = FastAPI(
    title="FindMyPath API Gateway",
    description="API Gateway with auth, rate limiting, and cost protection",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)


def handle_shutdown(signum, frame):
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()


signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="ok",
        timestamp=datetime.utcnow().isoformat(),
        version=settings.APP_VERSION,
    )


@app.get("/ready", response_model=ReadinessResponse)
async def readiness_check():
    redis_status = "ok"
    backend_status = "ok"
    overall = "ready"

    try:
        from app.rate_limiter import get_redis_client

        r = get_redis_client()
        r.ping()
    except Exception:
        redis_status = "unavailable"
        overall = "degraded"

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.BACKEND_URL}/health")
            if resp.status_code != 200:
                backend_status = "error"
                overall = "not_ready"
    except Exception:
        backend_status = "unreachable"
        overall = "not_ready"

    return ReadinessResponse(status=overall, redis=redis_status, backend=backend_status)


@app.post("/ask")
async def ask(
    body: AskRequest,
    request: Request,
    _=Depends(verify_api_key),
    __=Depends(check_rate_limit),
):
    ok, cost_info = check_cost_limit()
    if not ok:
        return JSONResponse(
            status_code=429, content={"error": cost_info["message"], "cost": cost_info}
        )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "message": body.question,
                "session_id": body.session_id,
                "user_context": {"user_id": body.user_id},
            }
            resp = await client.post(
                f"{settings.BACKEND_URL}/api/v1/agents/chat", json=payload
            )
            result = resp.json()

        spent = record_request_cost()

        return {
            "data": result,
            "cost": {
                "request_cost": settings.COST_PER_REQUEST,
                "total_spent": spent,
                "limit": settings.COST_LIMIT_USD,
            },
        }

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Backend timeout")
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Backend unreachable")
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.post("/ask/stream")
async def ask_stream(
    body: AskRequest,
    request: Request,
    _=Depends(verify_api_key),
    __=Depends(check_rate_limit),
):
    ok, cost_info = check_cost_limit()
    if not ok:
        return JSONResponse(
            status_code=429, content={"error": cost_info["message"], "cost": cost_info}
        )

    async def event_generator():
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "message": body.question,
                    "session_id": body.session_id,
                    "user_context": {"user_id": body.user_id},
                }
                async with client.stream(
                    "POST",
                    f"{settings.BACKEND_URL}/api/v1/agents/chat/stream",
                    json=payload,
                ) as resp:
                    async for line in resp.aiter_lines():
                        if shutdown_event.is_set():
                            break
                        yield f"{line}\n"

            record_request_cost()

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f'data: {{"type":"error","message":"{str(e)}"}}\n\n'

    return event_generator()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = datetime.utcnow()
    response = await call_next(request)
    duration = (datetime.utcnow() - start).total_seconds()
    logger.info(
        f"{request.method} {request.url.path} -> {response.status_code} ({duration:.3f}s)"
    )
    return response
