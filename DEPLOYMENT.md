# Deployment Information — Day 12 Lab

> **Student Name:** Nông Nguyễn Thành  
> **Student ID:** 2A202600250
> **Date:** 17/04/2026

---

## Public URL

**https://vinai-day12.thanhnn.dev**

---

## Platform

**VPS (Self-Hosted)** — Deployed on an Ubuntu VPS purchased from MegaHost.vn, with full stack managed via Docker Compose. Not using managed platforms (Railway/Render/Cloud Run). Managed via aaPanel control panel for simplified deployment, Nginx configuration, and SSL certificate management. The API Gateway pattern runs behind Nginx reverse proxy with Let's Encrypt SSL termination.

### Architecture

```
Internet
    │
    ▼
┌─────────────────────────────────────────┐
│  Nginx (Reverse Proxy + SSL Termination) │
│  vinai-day12.thanhnn.dev → localhost     │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  API Wrapper (Port 18001)                │
│  ├─ API Key Authentication               │
│  ├─ Rate Limiting (10 req/min)           │
│  ├─ Cost Guard ($10/month)               │
│  └─ Request Validation                   │
└──────┬──────────────────────┬───────────┘
       │                      │
       ▼                      ▼
┌──────────────┐    ┌──────────────────────┐
│  Redis        │    │  Backend (Port 18000) │
│  (Rate limit  │    │  FindMyPath Agent     │
│   counters,   │    │  - PDF Generation     │
│   cost tracking│   │  - Template Engine    │
│   & sessions) │    │  - LLM Integration    │
└──────────────┘    └──────────────────────┘
```

### Service Components

| Service        | Internal Port | External Port | Description                        |
|----------------|---------------|---------------|------------------------------------|
| Nginx          | 80/443        | 80/443        | Reverse proxy, SSL termination     |
| API Wrapper    | 18001         | 18001*        | Auth, rate limiting, cost guards   |
| Backend Agent  | 18000         | 18000*        | FindMyPath agent logic             |
| Redis          | 6379          | 6379*         | Rate limit counters, cost tracking |

> *Internal ports exposed for local testing. In production, only Nginx (443) is publicly accessible.

---

## Test Commands

### Health Check

```bash
curl https://vinai-day12.thanhnn.dev/health
# Expected: {"status": "ok", "uptime": "...", "timestamp": "..."}
```

### Authentication Required (should fail)

```bash
curl https://vinai-day12.thanhnn.dev/ask
# Expected: 401 Unauthorized
# Response: {"error": "API key required"}
```

### API Test (with authentication)

```bash
curl -X POST https://vinai-day12.thanhnn.dev/ask \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test-user", "question": "Hello, can you help me?"}'
# Expected: 200 OK with agent response
```

### Invalid API Key (should fail)

```bash
curl -X POST https://vinai-day12.thanhnn.dev/ask \
  -H "X-API-Key: invalid-key" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test-user", "question": "Hello"}'
# Expected: 401 Unauthorized
# Response: {"error": "Invalid API key"}
```

### Rate Limiting

```bash
# Send 15 rapid requests — should hit 429 after 10
for i in $(seq 1 15); do
  echo "Request $i:"
  curl -s -o /dev/null -w "HTTP %{http_code}\n" \
    -X POST https://vinai-day12.thanhnn.dev/ask \
    -H "X-API-Key: YOUR_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"user_id": "test-user", "question": "rate limit test"}'
done
# Expected: First 10 return 200, subsequent return 429 Too Many Requests
```

### Cost Guard Check

```bash
# After exceeding monthly cost limit ($10):
curl -X POST https://vinai-day12.thanhnn.dev/ask \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test-user", "question": "cost check"}'
# Expected: 429 or 503 with cost limit exceeded message
```

---

## Configuration (.env.example)

All configuration is managed via `.env` file on the VPS, based on the `.env.example` template committed in the repository. Each service has its own set of environment variables.

### API Wrapper (Port 18001) — Security Gateway

| Variable              | Value (example)                    | Purpose                            |
|-----------------------|------------------------------------|------------------------------------|
| `PORT`                | `18001`                            | API Wrapper listen port            |
| `AGENT_API_KEY`       | *(set, not disclosed)*             | API key for client authentication  |
| `REDIS_URL`           | `redis://redis:6379/0`             | Redis connection for rate limiting |
| `BACKEND_URL`         | `http://findmypath:18000`          | Internal backend service URL       |
| `RATE_LIMIT_REQUESTS` | `10`                               | Max requests per window            |
| `RATE_LIMIT_WINDOW`   | `60`                               | Rate limit window (seconds)        |
| `COST_LIMIT_USD`      | `10.0`                             | Monthly cost cap                   |
| `COST_PER_REQUEST`    | `0.05`                             | Estimated cost per request         |
| `LOG_LEVEL`           | `info`                             | Application logging verbosity      |

### Backend Agent (Port 18000) — FindMyPath LangGraph

| Variable            | Value (example)                    | Purpose                            |
|---------------------|------------------------------------|------------------------------------|
| `OPENAI_API_KEY`    | *(set, not disclosed)*             | OpenAI API key for LLM calls       |
| `OPENAI_MODEL`      | `gpt-4-turbo-preview`              | Default LLM model                  |
| `PDF_OUTPUT_DIR`    | `./output/pdfs`                    | Generated PDF storage path         |
| `TEMPLATE_DIR`      | `./src/templates`                  | Document template directory        |

> **Note:** The API Wrapper does NOT need `OPENAI_API_KEY` — it only handles auth, rate limiting, and proxying. The Backend Agent does NOT need `AGENT_API_KEY` — authentication is handled by the gateway layer.

---

## Deployment Steps (VPS)

### Prerequisites

- Ubuntu 22.04+ VPS with Docker & Docker Compose installed
- Domain `vinai-day12.thanhnn.dev` pointing to VPS IP
- Nginx installed
- Certbot installed

### Step 1: Clone & Configure

```bash
# SSH into VPS
ssh user@your-vps-ip

# Clone repository
git clone https://github.com/thanhnndev/2A202600250-Day12.git
cd 2A202600250-Day12/api-wrapper

# Create .env from template
cp .env.example .env
nano .env
```

Fill in the `.env` file — it must contain **both** service configurations since `docker-compose.yml` reads from this single file and distributes variables to each container:

```env
# ── API Wrapper ──
AGENT_API_KEY=sk-your-secret-key-here
REDIS_URL=redis://redis:6379/0
BACKEND_URL=http://findmypath:18000
RATE_LIMIT_REQUESTS=10
RATE_LIMIT_WINDOW=60
COST_LIMIT_USD=10.0
COST_PER_REQUEST=0.05
LOG_LEVEL=info

# ── Backend Agent ──
OPENAI_API_KEY=sk-proj-your-openai-key-here
OPENAI_MODEL=gpt-4-turbo-preview
```

> **Important:** `AGENT_API_KEY` and `OPENAI_API_KEY` are separate. The wrapper uses `AGENT_API_KEY` to authenticate clients. The agent uses `OPENAI_API_KEY` to call OpenAI. They are NOT interchangeable.

### Step 2: Start Services with Docker Compose

```bash
# Build and start all services
docker compose up -d --build

# Verify all containers running
docker compose ps

# Check logs
docker compose logs -f api-wrapper
```

Expected output:
```
NAME                        STATUS
api-wrapper-api-wrapper-1   Up (healthy)
api-wrapper-findmypath-1    Up
api-wrapper-redis-1         Up (healthy)
```

### Step 2.5: DNS Configuration

The domain `vinai-day12.thanhnn.dev` is pointed to the VPS IP via an **A record** in the DNS provider:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A    | vinai-day12 | [VPS_IP] | Auto |

This routes all traffic to the VPS, where Nginx reverse proxy forwards requests to the API Wrapper container on port 18001.

### Step 3: Configure Nginx Reverse Proxy (via aaPanel)

Using aaPanel's Website feature:
- Add site `vinai-day12.thanhnn.dev`
- Apply Let's Encrypt SSL certificate (auto via aaPanel)
- Set reverse proxy to `http://127.0.0.1:18001`
- Enable Force HTTPS redirect

### Step 4: Verify Deployment

```bash
# Test health endpoint
curl https://vinai-day12.thanhnn.dev/health

# Test with API key
curl -X POST https://vinai-day12.thanhnn.dev/ask \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "deploy-test", "question": "Deployment verification"}'
```

---

## Ongoing Operations

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api-wrapper
docker compose logs -f redis
```

### Restart Services

```bash
# Restart single service
docker compose restart api-wrapper

# Full rebuild and restart
docker compose down && docker compose up -d --build
```

### SSL Renewal

SSL renewal is auto-managed by aaPanel's Let's Encrypt integration.

### Monitoring

```bash
# Check container health
docker compose ps

# Check disk usage
docker system df

# Check Redis connections
docker compose exec redis redis-cli info clients
```

---

## aaPanel Management

The deployment is managed via aaPanel control panel on the Ubuntu VPS (MegaHost.vn), which handles Nginx reverse proxy configuration, Let's Encrypt SSL certificates, firewall rules, and server monitoring through a web-based dashboard.

---

## Screenshots

All screenshots are in the ` screenshots/` directory.

| # | File | Description |
|---|------|-------------|
| 1 | `docker-ps.png` | Docker Compose showing api-wrapper, findmypath, and redis all running (Up healthy) |
| 2 | `health-check.png` | `curl https://vinai-day12.thanhnn.dev/health` returning 200 OK with status "ok" |
| 3 | `api-test.png` | POST `/ask` with valid X-API-Key returning 200 OK with agent response |
| 4 | `rate-limit.png` | 15 rapid requests showing first 10 return 200, requests 11+ return 429 Too Many Requests |
| 5 | `ssl-cert.png` | Browser showing valid Let's Encrypt SSL certificate for vinai-day12.thanhnn.dev |
| 6 | `dashboard.png` | aaPanel control panel dashboard showing website configuration and server monitoring |
| 7 | `github-actions.png` | GitHub Actions CI/CD workflows all passing (lint, test, docker-build, security-scan, deploy) |

### Screenshots Directory

```
 screenshots/
├── docker-ps.png
├── health-check.png
├── api-test.png
├── rate-limit.png
├── ssl-cert.png
├── dashboard.png
└── github-actions.png
```

### Verification

All 7 screenshots captured on 17/04/2026 confirming the deployment is live and all features working.

---

## Security Notes

- [x] No `.env` file committed (only `.env.example` in repo)
- [x] No hardcoded secrets in source code
- [x] API key authentication required for all endpoints
- [x] Rate limiting enforced (10 req/min per user)
- [x] Cost guard enabled ($10/month cap)
- [x] HTTPS enforced via Let's Encrypt
- [x] Security headers configured (HSTS, X-Frame-Options, X-Content-Type-Options)
- [x] Internal services not directly exposed (only Nginx on 443)
- [x] Redis volume persisted for data durability
- [x] Services set to `restart: unless-stopped`

---

## Troubleshooting

| Issue                        | Resolution                                                   |
|------------------------------|--------------------------------------------------------------|
| 502 Bad Gateway              | Check `docker compose ps` — backend may be down              |
| SSL certificate expired      | Run `sudo certbot renew` and reload Nginx                    |
| 401 Unauthorized             | Verify `AGENT_API_KEY` in `.env` matches request header      |
| 429 Too Many Requests        | Rate limit hit — wait 60s or check Redis counters            |
| Connection refused on 18001  | Verify API Wrapper container is running: `docker compose ps` |
| Redis connection errors      | Check Redis health: `docker compose exec redis redis-cli ping`|

---

## Quick Tips

1. Test your public URL from a different device or network
2. Include screenshots of working deployment in `screenshots/` folder
3. Write clear commit messages for all changes
4. Test all commands in this document work as expected
5. No secrets in code or commit history
6. Set up monitoring/alerting for production use

---

**Deployment Status:** Live
**Last Updated:** 17/04/2026
