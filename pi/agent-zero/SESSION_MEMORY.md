# Session Memory — Full Stack Context

## Render Hermes Deployment
- **Repo**: https://github.com/johanneslungelo021-cmd/render-hermes
- **URL**: https://render-hermes.onrender.com (health check OK, dashboard building)
- **Latest commit**: d669f97e — GitHub Actions + web dist fix + all services wired
- **43 skills bundled** in pi/skills/

## Browser Stack (Eigent + pi browser-tools)
- **Chrome**: Playwright Chromium 149 at ~/.cache/ms-playwright/chromium-1228/chrome-linux/chrome
- **CDP port**: Dynamic (9233-9236 tested working)
- **Fix**: Playwright path added first in CHROME_CANDIDATES; snap chromium-browser moved to last resort
- **Status**: ✅ Working

## A2A Agent Protocol
- **Files**: a2a_core.py, a2a_memory.py, a2a_tmux.py, a2a_agent.py, a2a-server.py, a2a-task-worker.py
- **Web UI**: Port 8086 (via Cloudflare tunnel)
- **Memory**: Qdrant + Mistral embeddings + Supabase logging
- **Subordinates**: tmux-ready

## Services Wired to Hermes
| Service | Method |
|---------|--------|
| Qdrant | Memory provider (vector store) |
| Supabase | MCP HTTP server |
| n8n | MCP HTTP server |
| Redis Cloud | Env var |
| NATS+JetStream | Env vars |
| Caddy | Env vars |
| Grafana | Env vars |

## API Keys
- OpenCode: sk-BYvG5nYkCJDPNjOejx2ThEcliOYcrUp8QQEqDobcVtncGGT47WQXrKNwopJiF97c
- Mistral: dU3kS44SXmMmaQzYt8f9PPq0YHEmBTaP
- MiMo (Xiaomi): sk-sqrb9gpiffbahukcvuyrbvtjl873tc96na16fdylvtgabxzl
- Render API: rnd_DGwIPGcodTEROkzxEp7fZln2wI6E
