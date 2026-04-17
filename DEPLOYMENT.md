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

## Environment Variables Set

| Variable              | Value (example)                    | Purpose                            |
|-----------------------|------------------------------------|------------------------------------|
| `PORT`                | `18001`                            | API Wrapper listen port            |
| `REDIS_URL`           | `redis://redis:6379/0`             | Redis connection for rate limiting |
| `AGENT_API_KEY`       | *(set, not disclosed)*             | API key for authentication         |
| `LOG_LEVEL`           | `info`                             | Application logging verbosity      |
| `BACKEND_URL`         | `http://findmypath:18000`          | Internal backend service URL       |
| `RATE_LIMIT_REQUESTS` | `10`                               | Max requests per window            |
| `RATE_LIMIT_WINDOW`   | `60`                               | Rate limit window (seconds)        |
| `COST_LIMIT_USD`      | `10.0`                             | Monthly cost cap                   |
| `COST_PER_REQUEST`    | `0.05`                             | Estimated cost per request         |
| `OPENAI_API_KEY`      | *(set, not disclosed)*             | Backend LLM provider key           |
| `OPENAI_MODEL`        | `gpt-4-turbo-preview`              | Default LLM model                  |

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
nano .env  # Fill in AGENT_API_KEY, OPENAI_API_KEY, etc.
```

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

### Step 3: Configure aaPanel Reverse Proxy

Using aaPanel control panel:

1. **Add Website** — In aaPanel → Website → Add Site:
   - Domain: `vinai-day12.thanhnn.dev`
   - Root directory: default (not used for reverse proxy)
   - PHP version: Pure Static (no PHP needed)

2. **Apply SSL Certificate** — In aaPanel → Website → vinai-day12.thanhnn.dev → SSL:
   - Select "Let's Encrypt"
   - Click "Apply" to auto-generate and install certificate
   - Enable "Force HTTPS" redirect

3. **Set Reverse Proxy** — In aaPanel → Website → vinai-day12.thanhnn.dev → Reverse Proxy:
   - Proxy name: `api-wrapper`
   - Target URL: `http://127.0.0.1:18001`
   - Enable proxy and save

### Step 4: SSL Certificate (Let's Encrypt)

```bash
# Obtain certificate
sudo certbot certonly --webroot \
  -w /var/www/certbot \
  -d vinai-day12.thanhnn.dev \
  --email your-email@example.com \
  --agree-tos \
  --non-interactive

# Verify certificate
sudo certbot certificates

# Set up auto-renewal (usually pre-configured)
sudo systemctl status certbot.timer
```

### Step 5: Verify Deployment

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

```bash
# Dry-run test
sudo certbot renew --dry-run

# Manual renewal
sudo certbot renew && sudo systemctl reload nginx
```

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

Deployment is managed through aaPanel control panel:

- **Website** — Reverse proxy configuration for vinai-day12.thanhnn.dev
- **SSL** — Auto-applied Let's Encrypt certificate via aaPanel
- **Docker** — Docker Compose managed via SSH terminal in aaPanel
- **Monitor** — CPU, memory, disk, and network monitoring via aaPanel dashboard
- **Firewall** — Port management via aaPanel Security section

---

## Screenshots

> **Note:** This is a VPS (self-hosted) deployment. Screenshots should be captured from:
>
> 1. **`screenshots/nginx-config.png`** — Nginx configuration showing reverse proxy setup
> 2. **`screenshots/docker-ps.png`** — Docker Compose showing all services running
> 3. **`screenshots/health-check.png`** — curl health check returning 200 OK
> 4. **`screenshots/api-test.png`** — Successful API call with authentication
> 5. **`screenshots/rate-limit.png`** — Rate limiting test showing 429 response
> 6. **`screenshots/ssl-cert.png`** — Browser showing valid Let's Encrypt SSL certificate
> 7. **`screenshots/certbot-status.png`** — Certbot certificate status and auto-renewal

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
