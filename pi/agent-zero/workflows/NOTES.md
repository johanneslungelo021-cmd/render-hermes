# Workflow Notes — User's World

## Identity & Goals

- Aspiring professional trader
- Uses Smart Money Concepts (SMC) trading style
- Interested in prop firms (FTMO, etc.)
- Runs a Numerai ML agent for signal generation
- Fact-checks social media misinformation
- South Africa based (SAIIA for local news)

## Tools & Accounts

| Tool | Purpose | Access |
|------|---------|--------|
| TradingView | Chart analysis, SMC setups | Web |
| Numerai | ML-based hedge fund signals | Kaggle API + local agent |
| Kaggle | Datasets, Numerai tournament data | ✅ API key (lungelo-luda) |
| Agent Zero | AI agent orchestration | ✅ Cloudflare tunnel + Mistral |
| A0 CLI | Host bridge (code exec, files) | ✅ Connected |
| Eigent Browser | CDP-controlled Chrome 149 | ✅ Running on :9222 |
| Telegram Bot | Notifications/alerts | ✅ Connected to Agent Zero |

## Tools & Techniques

### Browser Stack (Eigent + pi browser-tools)
- Chromium 149 at `/root/.cache/ms-playwright/chromium-1228/chrome-linux/chrome`
- Xvfb support for stealth mode (bypasses headless detection)
- CDP via `chrome-remote-interface` on port 9222
- Profile injection: `--profile` flag copies Chrome profile into scratch dir
- Tested: 19/19 tests passing

### Machine Learning Stack
- Kaggle API for Numerai tournament data
- Python ML stack available
- Numerai agent (local)

### Infrastructure
- PRoot Ubuntu (Termux) — no Docker daemon
- Cloudflare tunnel to Agent Zero instance (GCP Cloud Shell)
- Mistral AI for LLM (mistral-large-latest)

## Recurring Activities

1. **Market Research** — stocks, crypto, forex, commodities analysis via TradingView
2. **Local News Intel** — SAIIA for South African geo-political context
3. **SMC Analysis** — Order blocks, liquidity, FVG, CHoCH on multiple timeframes
4. **Numerai Pipeline** — Download data, train models, submit predictions
5. **Fact Checking** — Verify claims, detect social media misinformation
6. **Prop Firm Prep** — Trading within drawdown limits, profit targets

## Terminology

| Term | Meaning |
|------|---------|
| SMC | Smart Money Concepts — trading methodology |
| FVG | Fair Value Gap |
| BOS | Break of Structure |
| CHoCH | Change of Character |
| OB | Order Block |
| Prop Firm | Proprietary trading firm (FTMO, etc.) |
| Numerai | ML hedge fund — tournament-based model submission |
| SAIIA | South African Institute of International Affairs |
