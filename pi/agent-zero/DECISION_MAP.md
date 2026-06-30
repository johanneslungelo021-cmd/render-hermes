# Decision Map — Trader Intelligence Stack

## Vision
An automated intelligence pipeline that combines Numerai ML signals, SMC technical analysis, geo-political news intel, and fact-checking into a single trading workflow — all orchestrated through Agent Zero with browser automation, Kaggle API, Telegram, and A0 CLI.

## The Stack
```
Numerai (ML signals) ─┐
TradingView (SMC) ────┤──→ Agent Zero (Mistral) ──→ Brief → Telegram
SAIIA (news intel) ───┤                                            
Fact-check ───────────┘                                            
```

## Frontier (Open Tickets)

### #1: Numerai Agent Integration

Blocked by: none
Type: Prototype

#### Question
What's the current state of the Numerai agent? Is it a Python script, a notebook, or something else? Where does it live? What model architecture does it use (LightGBM, XGBoost, neural network)? 

#### Answer
*[To be resolved]*

---

### #2: TradingView Browser Automation

Blocked by: none  
Type: Prototype

#### Question
Can the Eigent browser stack reliably navigate TradingView, apply chart templates, and extract structured data (levels, patterns)? TradingView is a heavy SPA — need to verify CDP-based automation works for:
- Loading a chart with specific symbol/ timeframe
- Reading on-screen price levels
- Capturing screenshots

#### Answer
*[To be resolved]*

---

### #3: Workflow Orchestration Engine

Blocked by: #1, #2
Type: Research | Prototype

#### Question
How should the workflows be triggered and chained?
- Agent Zero as the orchestrator (it calls tools via A0 CLI)?
- A Python scheduler (cron + scripts) that feeds into Agent Zero for analysis?
- Telegram bot as the primary interface?

Options:
- **Telegram-first:** User sends `/research` → triggers full pipeline → gets brief back
- **Scheduled:** Cron job runs at 07:00 → Agent Zero processes → brief saved
- **Agent Zero as controller:** Agent Zero decides when to run each workflow

#### Answer
*[To be resolved]*

---

### #4: Data Storage & Brief Format

Blocked by: none
Type: Research

#### Question
Where should briefs, trade plans, and analysis be stored?
- Local filesystem (`/root/trading/`)?
- Agent Zero's memory system?
- Git-tracked markdown files for accountability?
- A combination?

#### Answer
*[To be resolved]*

---

### #5: Fact-Checking Data Sources

Blocked by: none
Type: Research

#### Question
Which fact-checking APIs/sources are accessible without API keys?
- Africa Check (API?)
- Reuters Fact Check (RSS?)
- SAIIA website (scrape?)
- Google Fact Check Tools API (needs key?)

Need to audit what's freely available vs what needs credentials.

#### Answer
*[To be resolved]*

---

### #6: SAIIA News Scraping

Blocked by: none
Type: Prototype

#### Question
Can the browser automation reliably scrape SAIIA's website for latest articles? Need to verify:
- Page structure
- Anti-scraping measures
- Update frequency
- Article format

#### Answer
*[To be resolved]*

---

## Resolved

*(none yet — this is the bootstrap)*
