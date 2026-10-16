# MinecraftAI Production Deployment Guide

This guide details the deployment architecture, configuration parameters, resource requirements, and operational practices for hosting MinecraftAI as a public, zero-setup web application.

---

## 1. Zero-Setup Architecture Overview

In production, MinecraftAI operates with a strict server-side AI execution model. End-users interacting with the web application require zero local setup:

```text
Browser Client (No Python, No Ollama, No API Keys)
       │
       │ HTTPS (Port 443)
       ▼
Reverse Proxy / Ingress (Caddy / Nginx / Cloudflare)
       │
       │ HTTP (Internal Port 8000)
       ▼
MinecraftAI Container (FastAPI + Non-Root User: appuser)
       │
       │ HTTPS + Server-Side Bearer Token (OLLAMA_API_KEY)
       ▼
Server-Side AI Provider (Ollama Cloud / Remote Endpoint)
       │
       ▼
Deterministic Pipeline (AI Understanding → Planning → Generation → QA → ZIP)
       │
       ▼
Generated Datapack Archive (/api/download/{filename}.zip)
```

**Security Invariants:**
* Client browsers never receive the AI provider credentials or API keys.
* Client browsers never communicate directly with the AI model provider.
* Internal filesystem paths (e.g. server directories) are concealed in production responses.
* The public container runs as unprivileged `appuser` (UID 10001).

---

## 2. Server Resource Sizing & Capacity Realities

Deploying a public AI generation platform requires realistic resource allocation:

### Hardware Specifications

| Component | Minimum (Staging / Low Traffic) | Recommended (Public Production) | Notes |
| :--- | :--- | :--- | :--- |
| **CPU** | 2 vCPUs | 4 - 8 vCPUs | Pipeline validation, AST parsing, and ZIP generation are CPU-bound |
| **RAM** | 2 GB | 4 - 8 GB | Fast memory consumption per request: ~150-250 MB |
| **Disk Storage** | 20 GB SSD | 50 GB NVMe SSD | Temporary datapack archive storage with auto-retention cleanup |
| **Network** | 50 Mbps | 1 Gbps | Outbound HTTPS calls to AI cloud; inbound user ZIP downloads |

### Operational Reality & Capacity
* **Generation Latency:** Cloud AI provider round-trips typically take **3 to 15 seconds** per generation depending on prompt complexity.
* **Concurrency Cap:** The default `MC_MAX_CONCURRENT_GENERATIONS` is set to **4** concurrent tasks. This prevents worker starvation and outbound rate-limiting issues on cloud providers.
* **Throughput:** With a 10s average generation time and concurrency cap of 4, a single server handles ~24 generations/minute.
* **Storage Footprint:** Average generated ZIP archive is ~20 KB. 1,000 generations require ~20 MB. Automatic hourly cleanup (`MC_ARTIFACT_RETENTION_SECONDS=3600`) ensures disk storage remains lean.

---

## 3. Environment Variables & Secret Configuration

Production secrets must be managed via your hosting platform's environment/secret manager (e.g., Docker Swarm Secrets, Kubernetes Secrets, AWS Secrets Manager, GitHub Actions Environments, or systemd EnvironmentFile).

### Core Server Settings

| Variable | Default | Recommended Production Value | Description |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | `development` | `production` | Enables production error sanitization and conceals server paths |
| `HOST` | `127.0.0.1` | `0.0.0.0` | Container network bind interface |
| `PORT` | `8000` | `8000` | Internal listening port |
| `PUBLIC_ORIGIN` | `*` | `https://your-domain.com` | Strict CORS origin configuration |

### Server-Side AI Provider Settings

| Variable | Example Value | Description |
| :--- | :--- | :--- |
| `LLM_PROVIDER` | `ollama` | Provider backend (`ollama` or `openai`) |
| `OLLAMA_HOST` | `https://ollama.com` | Remote Ollama Cloud endpoint |
| `OLLAMA_MODEL` | `gpt-oss:120b-cloud` | Cloud model identifier |
| `OLLAMA_API_KEY` | `<SECRET>` | **Private server API credential (Never expose!)** |

### Security & Rate-Limiting Controls

| Variable | Default | Recommended Production Value | Description |
| :--- | :--- | :--- | :--- |
| `MC_MAX_PROMPT_LENGTH` | `2000` | `2000` | Rejects oversized requests |
| `MC_RATE_LIMIT_PER_MINUTE`| `30` | `30` | Sliding-window requests per IP |
| `MC_BURST_ALLOWANCE` | `10` | `10` | Instantaneous request burst allowance |
| `MC_MAX_CONCURRENT_GENERATIONS` | `4` | `4` | Maximum parallel AI pipeline runs |
| `MC_GENERATION_TIMEOUT_SECONDS` | `60.0` | `60.0` | Maximum seconds before timing out |
| `MC_ARTIFACT_RETENTION_SECONDS` | `3600` | `3600` | Archive expiration threshold (1 hour) |

---

## 4. Docker Deployment

### Step 1: Prepare Server Configuration
On your production host:
```bash
# Clone the repository
git clone https://github.com/krishnabhardwaj-001/MinecraftAI.git /opt/minecraftai
cd /opt/minecraftai

# Create production environment file with secure permissions
cat << 'EOF' > .env
ENVIRONMENT=production
HOST=0.0.0.0
PORT=8000
PUBLIC_ORIGIN=https://minecraft.example.com
LLM_PROVIDER=ollama
OLLAMA_HOST=https://ollama.com
OLLAMA_MODEL=gpt-oss:120b-cloud
OLLAMA_API_KEY=YOUR_PRODUCTION_SECRET_KEY_HERE
MC_RATE_LIMIT_PER_MINUTE=30
MC_MAX_CONCURRENT_GENERATIONS=4
MC_ARTIFACT_RETENTION_SECONDS=3600
EOF

chmod 600 .env
```

### Step 2: Build and Run
```bash
docker compose up -d --build
```

### Step 3: Verify Container Health
```bash
docker compose ps
docker compose logs -f minecraft-ai
curl -s http://localhost:8000/api/health | jq .
```

---

## 5. Reverse Proxy Configuration (HTTPS / SSL)

Never expose FastAPI directly to the public internet on port 80/443 without an SSL reverse proxy.

### Option A: Caddy (Recommended for automated Let's Encrypt SSL)

```caddy
minecraft.example.com {
    reverse_proxy 127.0.0.1:8000 {
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto https
    }

    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
    }

    request_body {
        max_size 10MB
    }
}
```

### Option B: Nginx

```nginx
server {
    listen 80;
    server_name minecraft.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name minecraft.example.com;

    ssl_certificate /etc/letsencrypt/live/minecraft.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/minecraft.example.com/privkey.pem;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 90s;
        proxy_connect_timeout 10s;
    }
}
```

---

## 6. Health Checks & Monitoring

The health check endpoint `/api/health` reports status without disclosing secrets:

```bash
curl -I https://minecraft.example.com/api/health
```

Expected JSON response:
```json
{
  "status": "ok",
  "health": "healthy",
  "edition": "Java Edition",
  "minecraft_version": "1.21.11",
  "generator": "ready",
  "validator": "ready",
  "pipeline": "ready",
  "security": "enforced",
  "rate_limiting": "active",
  "provider": "ollama"
}
```

---

## 7. Artifact Lifecycle & Disk Cleanup

* Generated datapacks and ZIP archives are created under `generated/`.
* The server automatically scans and purges artifacts older than `MC_ARTIFACT_RETENTION_SECONDS` (1 hour) on startup and during execution.
* If manual or cron-based cleanup is desired:
  ```bash
  # Cron entry to clean files older than 60 minutes
  0 * * * * find /opt/minecraftai/generated/ -mindepth 1 -mmin +60 -delete
  ```

---

## 8. Backup & Recovery

Because MinecraftAI is a deterministic stateless compiler:
* **No persistent database** is required.
* **Backup assets**: Only repository configuration, `.env`, and SSL certificates require backup.
* **Disaster Recovery**: Re-deploying a fresh container instance takes under 60 seconds.
