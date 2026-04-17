# FindMyPath API Gateway

API gateway wrapper for the FindMyPath AI agents with authentication, rate limiting, and cost protection.

## Features

- API Key authentication (`X-API-Key` header)
- Rate limiting: 10 requests/minute (Redis-backed)
- Cost guard: $10/month limit
- Health + readiness endpoints
- Graceful shutdown (SIGTERM/SIGINT)
- Stateless design (Redis session store)
- No hardcoded secrets

## Quick Start

### Docker Compose

```bash
cp .env.example .env
# Edit .env with your values
docker compose up -d
```

### Manual

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 18001
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/ready` | Readiness check (Redis + backend) |
| POST | `/ask` | Send question (requires API key) |
| POST | `/ask/stream` | Stream response (SSE) |

## Test Commands

```bash
# Health
curl http://localhost:18001/health

# Auth required (should return 401)
curl http://localhost:18001/ask

# With API key
curl -X POST http://localhost:18001/ask \
  -H "X-API-Key: sk-mock-day12-key-2026" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","question":"Hello"}'

# Rate limit test
for i in {1..15}; do 
  curl -X POST http://localhost:18001/ask \
    -H "X-API-Key: sk-mock-day12-key-2026" \
    -H "Content-Type: application/json" \
    -d '{"user_id":"test","question":"test"}'; 
done
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_API_KEY` | `sk-mock-day12-key-2026` | API key for authentication |
| `BACKEND_URL` | `http://findmypath:18000` | FindMyPath backend URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `RATE_LIMIT_REQUESTS` | `10` | Max requests per window |
| `RATE_LIMIT_WINDOW` | `60` | Rate limit window (seconds) |
| `COST_LIMIT_USD` | `10.0` | Monthly cost limit |
| `COST_PER_REQUEST` | `0.05` | Estimated cost per request |
| `LOG_LEVEL` | `info` | Logging level |
| `PORT` | `18001` | Server port |
