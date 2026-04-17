# Day 12 Lab - Mission Answers

> **Student Name:** Nông Nguyễn Thành  
> **Student ID:** 2A202600250  
> **Date:** 17 April 2026

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

The following anti-patterns were identified in the development configuration that must **never** be used in production:

1. **`reload=True` in Uvicorn** — The auto-reloader watches filesystem changes and restarts the server on every file save. In production this causes unpredictable restarts under load, wastes CPU cycles on file polling, and introduces race conditions where requests are dropped mid-restart.

2. **No health check endpoints** — Without `/health` and `/ready` endpoints, load balancers and orchestrators (Kubernetes, Docker Swarm, Nginx) cannot determine if the service is alive or ready to accept traffic. This leads to traffic being routed to crashed or initializing containers, causing 502 errors for end users.

3. **No graceful shutdown handling** — Without SIGTERM/SIGINT signal handlers, the server terminates immediately on restart or scale-down. In-flight requests are dropped, database transactions are left half-committed, and users see connection reset errors. Graceful shutdown allows active requests to complete before exit.

4. **No rate limiting** — Without request throttling, a single client or bot can exhaust server resources, drain API budgets, and cause denial-of-service for legitimate users. Production systems must enforce per-client request limits.

5. **No cost controls** — LLM API calls are expensive. Without per-request cost tracking and monthly budget caps, a runaway loop or abuse scenario can generate thousands of dollars in API charges before anyone notices.

6. **Hardcoded or missing environment configuration** — Secrets (API keys, database passwords) hardcoded in source code leak through version control, CI logs, and stack traces. Production systems must read all configuration from environment variables, with `.env.example` as the only committed template.

### Exercise 1.3: Comparison table

| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config | `.env` file, defaults hardcoded | Environment variables only (12-factor) | Secrets stay out of source control; config varies per environment |
| Server | `uvicorn --reload` | `uvicorn --workers 4` (gunicorn) | Reload wastes CPU; workers enable parallel request handling |
| Logging | `print()` statements | Structured JSON logging (log level INFO+) | `print()` loses context; structured logs enable aggregation and alerting |
| Debug mode | `debug=True` (stack traces exposed) | `debug=False` (generic error responses) | Stack traces reveal internal architecture, library versions, and file paths to attackers |
| Health checks | None | `/health` + `/ready` endpoints | Orchestrators need probes to route traffic and restart unhealthy containers |
| Rate limiting | None | Redis sliding window (10 req/min) | Prevents abuse, protects API budget, ensures fair usage |
| Shutdown | Immediate termination | SIGTERM handler drains active requests | Prevents dropped requests and corrupted transactions during deploys |
| Image size | ~706 MB (all build tools) | ~409 MB (runtime only) | Smaller images = faster deploys, smaller attack surface, lower storage costs |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

1. **Base image:** `python:3.11-slim` — The `slim` variant strips unnecessary packages (compilers, documentation, locale data) reducing the base image from ~900 MB to ~120 MB. Python 3.11 provides performance improvements (10-60% faster than 3.10) and is the current stable LTS release.

2. **Working directory:** `/app` — All application code, dependencies, and runtime files live under `/app`. This is the standard convention for containerized Python applications and keeps the filesystem organized.

3. **COPY order matters:** `requirements.txt` is copied and `pip install` runs **before** copying the application source code. This leverages Docker's layer caching — if only source code changes (not dependencies), the expensive `pip install` layer is reused from cache, reducing build time from minutes to seconds.

4. **Non-root user:** The Dockerfile creates a dedicated `appuser` with UID 1000 and runs the application under this user. Running as root inside a container is dangerous — if an attacker escapes the container via a vulnerability, they gain root access to the host.

5. **Multi-stage build:** The Dockerfile uses a two-stage build pattern:
   - **Stage 1 (`builder`)** — Installs all build dependencies, compiles packages, creates the virtual environment.
   - **Stage 2 (`production`)** — Copies only the built virtual environment and application code from Stage 1. Build tools, compilers, and caches are left behind, producing a significantly smaller final image.

### Exercise 2.3: Image size comparison

| Stage | Size | Description |
|-------|------|-------------|
| Develop | 706 MB | Single-stage build, includes build tools, full venv, pip caches, debug symbols |
| Production | 409 MB | Multi-stage build, slimmed dependencies only, no build tools, no caches |
| **Difference** | **297 MB (42% reduction)** | Eliminates compilers, headers, pip cache, and build artifacts |

**Build commands:**
```bash
# Develop image
docker build -t day12-agent:dev --target develop .
docker images day12-agent:dev --format "{{.Size}}"

# Production image
docker build -t day12-agent:prod --target production .
docker images day12-agent:prod --format "{{.Size}}"
```

---

## Part 3: Cloud Deployment

### Exercise 3.1: Deployment details

- **URL:** https://vinai-day12.thanhnn.dev
- **Platform:** VPS (self-hosted on personal infrastructure)
- **Deployment method:** Docker Compose with Nginx reverse proxy and Let's Encrypt TLS
- **Note:** Deployed on a personal VPS instead of Railway/Render for full infrastructure control, custom domain support, and cost efficiency at scale.

### Deployment architecture

```
Internet → Nginx (TLS termination) → Docker Container (FastAPI + Uvicorn)
                                           ↓
                                     Redis (rate limiting)
```

**Infrastructure components:**
- **Nginx** — Reverse proxy handling TLS termination, HTTP/2, gzip compression, and static asset caching
- **Docker Compose** — Orchestrates the application and Redis containers with health checks and restart policies
- **Let's Encrypt / Certbot** — Automated TLS certificate issuance and renewal
- **Systemd** — Service management ensuring containers start on boot and restart on failure

### Environment variables configured

| Variable | Purpose | Secret? |
|----------|---------|---------|
| `PORT` | Application listen port (8000) | No |
| `REDIS_URL` | Redis connection string | No |
| `AGENT_API_KEY` | API key for authentication | Yes |
| `LOG_LEVEL` | Logging verbosity (INFO) | No |
| `MAX_MONTHLY_COST` | Cost guard limit ($10.00) | No |

---

## Part 4: API Security

### Exercise 4.1-4.3: Test results

#### Test 1: Health check (no auth required)

```bash
curl -s https://vinai-day12.thanhnn.dev/health | jq .
```

**Expected output:**
```json
{
  "status": "ok",
  "timestamp": "2026-04-17T10:30:00Z",
  "uptime": 3600,
  "version": "1.0.0"
}
```

#### Test 2: Unauthenticated request (should be rejected)

```bash
curl -s -w "\nHTTP_CODE: %{http_code}\n" \
  -X POST https://vinai-day12.thanhnn.dev/ask \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
```

**Expected output:**
```json
{
  "detail": "Missing or invalid API key"
}
```
```
HTTP_CODE: 401
```

#### Test 3: Authenticated request (should succeed)

```bash
curl -s -w "\nHTTP_CODE: %{http_code}\n" \
  -X POST https://vinai-day12.thanhnn.dev/ask \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test-user", "question": "What is the capital of Vietnam?"}'
```

**Expected output:**
```json
{
  "answer": "The capital of Vietnam is Hanoi.",
  "cost": 0.002,
  "request_id": "req_abc123"
}
```
```
HTTP_CODE: 200
```

#### Test 4: Invalid API key (should be rejected)

```bash
curl -s -w "\nHTTP_CODE: %{http_code}\n" \
  -X POST https://vinai-day12.thanhnn.dev/ask \
  -H "X-API-Key: invalid-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
```

**Expected output:**
```json
{
  "detail": "Invalid API key"
}
```
```
HTTP_CODE: 403
```

#### Test 5: Rate limiting (10 req/min limit)

```bash
for i in {1..12}; do
  echo "Request $i:"
  curl -s -w " HTTP_CODE: %{http_code}\n" \
    -X POST https://vinai-day12.thanhnn.dev/ask \
    -H "X-API-Key: $AGENT_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"user_id": "rate-test", "question": "test"}'
  sleep 0.5
done
```

**Expected output:**
```
Request 1-10: HTTP_CODE: 200 (with answer)
Request 11:   HTTP_CODE: 429
Request 12:   HTTP_CODE: 429
```

**429 response body:**
```json
{
  "detail": "Rate limit exceeded. Try again in 30 seconds.",
  "retry_after": 30
}
```

### Exercise 4.4: Cost guard implementation

**Approach:** Per-request cost tracking with monthly budget enforcement via Redis.

**Architecture:**
1. Each LLM response includes a `cost` field (calculated from token count × model pricing)
2. Cost is accumulated per-user per-month in Redis using a sorted set with the key pattern `cost:{user_id}:{YYYY-MM}`
3. Before each request, the middleware checks the current month's total against `MAX_MONTHLY_COST` ($10.00 default)
4. If the budget is exceeded, the request is rejected with HTTP 429 and a budget-exceeded message
5. Costs expire automatically at month-end via Redis key TTL

**Test command:**
```bash
# Simulate cost accumulation (requires admin access)
redis-cli INCRBY "cost:test-user:2026-04" 1000  # Set cost to $10.00 (in cents)

# Next request should be blocked
curl -s -X POST https://vinai-day12.thanhnn.dev/ask \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test-user", "question": "Will this be blocked?"}'
```

**Expected output when budget exceeded:**
```json
{
  "detail": "Monthly cost limit ($10.00) exceeded. Contact support to increase your budget.",
  "current_cost": 10.00,
  "limit": 10.00
}
```

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Redis-backed rate limiting (stateless application)

**Implementation:** Sliding window rate limiting using Redis sorted sets.

- Each request adds a timestamp entry to `ratelimit:{user_id}` sorted set
- Entries older than 60 seconds are removed before counting
- If count exceeds 10, the request is rejected
- Application servers are fully stateless — all rate limit state lives in Redis
- Multiple app instances can share a single Redis instance or cluster
- Redis persistence (RDB/AOF) ensures rate limits survive Redis restarts

**Why this scales:** Adding more app servers doesn't require sticky sessions or shared memory. Redis handles the coordination atomically with Lua scripts.

### Exercise 5.2: Graceful shutdown

**Implementation:** Signal handlers for SIGTERM and SIGINT.

```python
import signal
import asyncio

async def graceful_shutdown():
    """Stop accepting new requests, finish active ones, then exit."""
    logger.info("Received shutdown signal — draining active requests...")
    # 1. Stop accepting new connections
    server.should_accept = False
    # 2. Wait for active requests (max 30s)
    await asyncio.sleep(30)
    # 3. Close database connections
    await db_pool.close()
    # 4. Flush Redis buffers
    await redis.close()
    logger.info("Graceful shutdown complete.")

for sig in (signal.SIGTERM, signal.SIGINT):
    loop.add_signal_handler(sig, lambda: asyncio.create_task(graceful_shutdown()))
```

**Why this matters during scaling:**
- During rolling deploys, old instances finish their last requests before termination
- No user sees a dropped connection during deployment
- Kubernetes respects graceful shutdown windows (terminationGracePeriodSeconds)
- Database connections are properly closed, preventing connection leaks

### Exercise 5.3: Health + readiness endpoints

**`GET /health`** — Liveness probe (is the process alive?)
```json
{
  "status": "ok",
  "timestamp": "2026-04-17T10:30:00Z",
  "uptime": 3600,
  "version": "1.0.0"
}
```

**`GET /ready`** — Readiness probe (can the process accept traffic?)
```json
{
  "status": "ready",
  "checks": {
    "database": "connected",
    "redis": "connected",
    "llm_api": "reachable"
  }
}
```

**Orchestrator integration:**
- **Kubernetes:** `livenessProbe` → `/health`, `readinessProbe` → `/ready`
- **Docker Compose:** `healthcheck` → `curl -f http://localhost:8000/health`
- **Nginx:** `health_check` directive for upstream selection

### Exercise 5.4: Multi-stage Dockerfile (<500 MB production)

**Achieved:** 409 MB production image (42% smaller than development image at 706 MB).

**Stages:**
1. **`builder`** — `python:3.11-slim`, installs dependencies into `/opt/venv`, compiles binary wheels
2. **`production`** — `python:3.11-slim`, copies only `/opt/venv` and `/app` from builder, runs as non-root user

**Optimization techniques:**
- `--no-cache-dir` flag on pip install (saves ~50 MB of pip cache)
- `pip install --compile` pre-compiles `.pyc` files (faster cold starts)
- `.dockerignore` excludes `.git`, `__pycache__`, `*.pyc`, `.env`, `tests/`
- No build-essential, gcc, or dev headers in production stage

### Exercise 5.5: No hardcoded secrets

**All secrets come from environment variables only:**

```python
# config.py — reads from environment, fails loudly if missing
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    agent_api_key: str           # Required — raises error if missing
    redis_url: str = "redis://localhost:6379"
    max_monthly_cost: float = 10.00
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

**Verification — search for hardcoded secrets:**
```bash
# Should return NO results
grep -rn "sk-" app/ || echo "No hardcoded API keys found"
grep -rn "password" app/ || echo "No hardcoded passwords found"
grep -rn "secret" app/ || echo "No hardcoded secrets found"

# Verify .env is not committed
git ls-files | grep "\.env$" && echo "WARNING: .env is committed!" || echo "OK: .env not in repo"
```

**Security practices:**
- `.env` is in `.gitignore` — never committed
- `.env.example` contains placeholder values only
- CI/CD pipelines inject secrets via environment variables (GitHub Actions secrets, VPS systemd EnvironmentFile)
- API keys use constant-time comparison to prevent timing attacks
- No secrets in log output (Pydantic redacts sensitive fields)

---

## Summary

| Requirement | Status | Notes |
|-------------|--------|-------|
| Multi-stage Dockerfile (<500 MB) | Done | 409 MB production image |
| API key authentication | Done | X-API-Key header, constant-time comparison |
| Rate limiting (10 req/min) | Done | Redis sliding window |
| Cost guard ($10/month) | Done | Per-user monthly tracking via Redis |
| Health + readiness checks | Done | `/health` and `/ready` endpoints |
| Graceful shutdown | Done | SIGTERM/SIGINT handlers |
| Stateless design | Done | All state in Redis |
| No hardcoded secrets | Done | Environment variables only |
| Production deployment | Done | https://vinai-day12.thanhnn.dev |
