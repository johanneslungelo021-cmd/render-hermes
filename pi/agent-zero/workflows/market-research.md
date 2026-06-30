# Workflow: Market Research Scan

## Trigger
Schedule: Daily at 07:00 SAST (before market opens)
Or on-demand via Telegram command `/research`

## Steps

### 1. Fetch Numerai Signals
- Use Kaggle API to download latest Numerai tournament data
- Run local Numerai agent to generate predictions
- Extract top/bottom signals as a watchlist

### 2. SMC Analysis Prep (TradingView)
- Browser automation navigates to TradingView
- Load watchlist from Numerai signals
- Capture key levels: order blocks, FVG, liquidity zones

### 3. SAIIA News Scan
- Navigate to SAIIA website (deep local news)
- Extract latest articles relevant to SA markets
- Summarize key geopolitical developments

### 4. Asset Class Scan
Check each class for high-impact events:
- **Stocks:** Major indices (JSE, S&P 500), sector movers
- **Crypto:** BTC dominance, top movers, on-chain metrics
- **Forex:** ZAR pairs, major fundamentals
- **Commodities:** Gold, oil, key agricultural

### 5. Brief Generation
Combine all findings into a single briefing document:
- Numerai signal summary (top/bottom predictions)
- SMC key levels identified
- News impacts (SAIIA + global)
- Asset class overview
- **Recommended bias** (bullish/bearish/neutral per asset)

## Output
Saved to `/root/trading/briefs/YYYY-MM-DD-brief.md`
OR sent via Telegram if urgent.

## Tools Used
- `kaggle` CLI — Numerai data download
- Python — Numerai model inference
- Eigent browser — TradingView, SAIIA, news scraping
- A0 CLI host code execution — data processing
- Mistral (Agent Zero) — summarization and analysis

## Checkpoints
1. **Numerai signals fetched** — auto, no review needed
2. **Brief generated** — user reviews before trading
3. **Alerts** — immediate Telegram notification for breaking news

## Push Right
All data gathering and analysis runs autonomously. User only sees the final brief.
