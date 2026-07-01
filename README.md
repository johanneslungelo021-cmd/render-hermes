# Render Hermes — Hermes Agent Deployed on Render

Deploy [Hermes Agent](https://github.com/NousResearch/hermes-agent) — an open-source AI coding agent by Nous Research — on [Render](https://render.com) with Telegram gateway, OpenCode provider, NumerAI pipeline, and Pi tooling.

## Architecture

```
┌──────────────────────────────────────────┐
│           Render (Docker)                │
│                                          │
│  ┌──────────────┐  ┌─────────────────┐  │
│  │ Health Check  │  │ Hermes Gateway  │  │
│  │ (port 8080)   │  │ (Telegram LP)   │  │
│  └──────────────┘  └────────┬────────┘  │
│                              │           │
│  ┌───────────────────────────▼────────┐ │
│  │      Hermes Agent Engine           │ │
│  │  (OpenCode / DeepSeek Provider)    │ │
│  └────────────────┬───────────────────┘ │
│                   │                     │
│  ┌────────────────▼───────────────────┐ │
│  │         Pi Tool Ecosystem          │ │
│  │  ┌─────────┐ ┌─────────┐          │ │
│  │  │ Memory  │ │  Nerve  │          │ │
│  │  │  Tool   │ │Dashboard│          │ │
│  │  └─────────┘ └─────────┘          │ │
│  │  ┌─────────┐ ┌─────────┐          │ │
│  │  │ Agent-  │ │ NumerAI │          │ │
│  │  │  Zero   │ │Pipeline │          │ │
│  │  └─────────┘ └─────────┘          │ │
│  └───────────────────────────────────┘ │
└──────────────────────────────────────────┘
```

## Features

- **Hermes Agent** — Full open-source AI agent with tool-use, code execution, web browsing
- **Telegram Gateway** — Control Hermes via Telegram (long-polling, no webhook needed)
- **OpenCode Provider** — Free deepseek-v4 models via [opencode.ai](https://opencode.ai)
- **Mistral Vision** — Pixtral-12b for image understanding
- **Pi Tooling** — Memory tool, Nerve dashboard, A2A ecosystem, Agent-Zero workflows
- **NumerAI Pipeline** — Ensemble prediction model with auto-submission
- **Kaggle CLI** — Pre-installed for data science workflows
- **Health Check** — Lightweight HTTP server keeps Render from sleeping

## Quick Deploy

### Prerequisites

1. [Render account](https://render.com)
2. [OpenCode API key](https://opencode.ai) (free)
3. [Telegram Bot Token](https://t.me/botfather)

### Deploy to Render

1. Fork/clone this repo
2. Connect repo to Render as a **Web Service**
3. Set **Runtime** → `Docker`
4. Add required environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENCODE_API_KEY` | ✅ | OpenCode API key |
| `TELEGRAM_BOT_TOKEN` | ✅ | Telegram bot token |
| `HERMES_PASSWORD` | Optional | Dashboard password |
| `MISTRAL_API_KEY` | Optional | For vision features |
| `NUMERAI_API_KEY` | Optional | NumerAI tournament |
| `KAGGLE_USERNAME` | Optional | Kaggle access |
| `KAGGLE_KEY` | Optional | Kaggle access |

### Local Build

```bash
docker build -t hermes-agent .
docker run -e OPENCODE_API_KEY=sk-... -e TELEGRAM_BOT_TOKEN=... -p 8080:8080 hermes-agent
```

## Interacting

### Via Telegram
Send messages to your bot. Hermes will respond with code execution, web search, file operations, and tool use.

### Health Check
```bash
curl https://your-service.onrender.com/
# → OK
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `PORT` | Health check port (default: 8080) |
| `DEFAULT_MODEL` | Model to use (default: deepseek-v4-flash-free) |
| `DEFAULT_PROVIDER` | Provider name (default: opencode) |
| `OPENCODE_API_KEY` | API key for OpenCode |
| `MISTRAL_API_KEY` | API key for Mistral (vision) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `HERMES_PASSWORD` | Dashboard basic auth password |
| `HERMES_DASHBOARD_USER` | Dashboard username (default: admin) |
| `HF_TOKEN` | HuggingFace token |
| `SUPABASE_URL` / `SUPABASE_KEY` | Supabase credentials |
| `NUMERAI_API_KEY` / `NUMERAI_MODEL_ID` / `NUMERAI_USERNAME` | NumerAI credentials |
| `KAGGLE_USERNAME` / `KAGGLE_KEY` | Kaggle credentials |
| `N8N_URL` / `N8N_API_KEY` | n8n workflow automation |
| `QDRANT_URL` / `QDRANT_API_KEY` | Qdrant vector store |

## License

MIT
