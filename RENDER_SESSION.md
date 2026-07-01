# Render Session — Hermes Agent Deployment

> Saved: 2026-07-01
> Repo: https://github.com/johanneslungelo021-cmd/render-hermes

## What This Is

Deploys [Hermes Agent](https://github.com/NousResearch/hermes-agent) (open-source AI agent by Nous Research) on **Render** with:
- **Telegram gateway** (long polling, no webhook)
- **OpenCode provider** (free deepseek-v4 models)
- **Pi tool ecosystem** (memory tool, nerve dashboard, agent-zero)
- **NumerAI pipeline** (ensemble prediction model)
- **Health check** to keep Render from sleeping

## Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Builds Hermes + Pi tools + NumerAI into a Docker image |
| `entrypoint.sh` | Starts health check server + Hermes Telegram gateway |
| `config.yaml` | Hermes config (providers, toolsets, agent settings) |
| `render.yaml` | Render blueprint (service config, env vars) |
| `pi/` | Pi tool ecosystem (memory, nerve, agent-zero) |
| `the-hidden-ledger/` | NumerAI prediction pipeline |

## Fixes Applied (Commit `71fad49`)

| # | Problem | Fix |
|---|---------|-----|
| 1 | `--yes` is NOT a valid install script flag → caused `exit 1` silently masked by `\|\| true` | Changed to `--skip-setup --non-interactive` |
| 2 | `hermes gateway run` doesn't exist | Changed to `hermes gateway` |
| 3 | `run_numerai.sh` referenced `.venv/bin/activate` (no venv in Docker) | Removed venv activation |
| 4 | Missing `numpy`, `pandas`, `scipy` for NumerAI | Added to `pip install` |
| 5 | No documentation | Created `README.md` |

## Deploy Instructions

### Option 1: Blueprint (recommended)

1. Go to [Render Dashboard](https://dashboard.render.com)
2. **New +** → **Blueprint**
3. Connect repo `johanneslungelo021-cmd/render-hermes`
4. Fill in secrets when prompted

### Option 2: Manual Web Service

1. **New +** → **Web Service**
2. Connect repo, **Runtime: Docker**
3. Set env vars:

### Required Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENCODE_API_KEY` | ✅ | OpenCode API key (free at [opencode.ai](https://opencode.ai)) |
| `TELEGRAM_BOT_TOKEN` | ✅ | Bot token from [@BotFather](https://t.me/botfather) |
| `HERMES_PASSWORD` | Optional | Dashboard password |
| `MISTRAL_API_KEY` | Optional | For vision features |

### Other Optional Variables (from `render.yaml`)

| Variable | Service | Purpose |
|----------|---------|---------|
| `QDRANT_URL` / `QDRANT_API_KEY` | **Qdrant** | Vector store (memory) |
| `SUPABASE_URL` / `SUPABASE_KEY` | **Supabase** | Database + Auth (MCP) |
| `N8N_URL` / `N8N_API_KEY` | **n8n** | Workflow automation (MCP) |
| `REDIS_URL` | **Redis Cloud** | Cache / KV store |
| `NATS_URL` / `NATS_CREDS` | **NATS+JetStream** | Message broker |
| `CADDY_URL` / `CADDY_API_KEY` | **Caddy** | Reverse proxy API |
| `GRAFANA_URL` / `GRAFANA_API_KEY` | **Grafana** | Monitoring dashboards |
| `HF_TOKEN` | HuggingFace | Model access |
| `NUMERAI_API_KEY` / `NUMERAI_MODEL_ID` / `NUMERAI_USERNAME` | NumerAI | Tournament predictions |
| `KAGGLE_USERNAME` / `KAGGLE_KEY` | Kaggle | Data science |

## Architecture

```
Render (Docker)
├── Health Check Server (port 8080) ← keeps Render alive
├── Hermes Gateway (Telegram long polling)
│   └── Hermes Agent Engine
│       ├── OpenCode Provider (deepseek-v4-flash-free)
│       └── Pi Tool Ecosystem
│           ├── Memory Tool
│           ├── Nerve Dashboard (React)
│           ├── Agent-Zero Workflows
│           └── NumerAI Pipeline
```

## API Keys Stored Locally

From `/root/.hermes/.env`:
- **OpenCode**: `sk-BYvG5nYkCJDPNjOejx2ThEcliOYcrUp8QQEqDobcVtncGGT47WQXrKNwopJiF97c`
- **MiMo (Xiaomi)**: `sk-sqrb9gpiffbahukcvuyrbvtjl873tc96na16fdylvtgabxzl`
- **Mistral**: `dU3kS44SXmMmaQzYt8f9PPq0YHEmBTaP`

## Config Providers

### OpenCode (default)
```
Base URL: https://opencode.ai/zen/v1
Models: deepseek-v4-flash-free, deepseek-v4-fast-free, deepseek-v4-pro
```

### MiMo (Xiaomi)
```
Base URL: https://api.xiaomimimo.com/v1
Models: MiMo-V2.5-Pro (try: mimo-v2-pro, mimo-v2-flash)
Key: XIAOMI_API_KEY
```

## Health Check

```bash
curl https://hermes-agent.onrender.com/
# → OK
```
