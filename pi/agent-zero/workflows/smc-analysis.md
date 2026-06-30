# Workflow: SMC Trading Analysis

## Trigger
On-demand: User requests analysis for a specific asset
Schedule: After daily market research brief

## SMC Framework (Smart Money Concepts)

### High Timeframe Bias (HTF — Daily/4H)
1. Identify overall trend direction
2. Mark key supply/demand zones
3. Note structural levels (BOS, CHoCH)

### Medium Timeframe Entry (MTF — 1H/15M)
1. Wait for HTF level to be tested
2. Look for liquidity sweep above/below previous swing
3. Identify order block (OB) at sweep point
4. Confirm with FVG (Fair Value Gap)

### Low Timeframe Execution (LTF — 5M/1M)
1. Entry on LTF confirmation
2. Stop loss beyond the swing point
3. Target: next liquidity zone or previous structure

## Automation Steps

### 1. Fetch Asset Watchlist
- From Numerai signals (top/bottom predictions)
- Or user-specified asset

### 2. Browser-Based Chart Analysis
Using Eigent browser + TradingView:
1. Open TradingView chart for asset
2. Apply HTF template (daily candles + key levels)
3. Capture screenshot of chart with annotations
4. Apply MTF template and capture
5. Apply LTF template and capture

### 3. Level Detection Algorithm
For each timeframe:
- Detect recent swing highs/lows
- Identify order blocks (last candle before strong move)
- Mark FVGs (3-candle gap pattern)
- Tag liquidity zones (above/below sweep points)

### 4. Setup Classification
Classify current price action into:
- **Ready to trade** — clear HTF bias + MTF setup + LTF entry triggered
- **Monitor** — approaching key level, no entry yet
- **No setup** — ranging, no clear structure

## Output
- Chart screenshots with marked levels
- Setup classification per asset
- Suggested trade plan (entry, SL, TP, risk %)

## Tools Used
- Eigent browser with Chrome 149
- TradingView web (chart analysis)
- Python for level calculation
- Agent Zero (Mistral) for pattern interpretation

## Checkpoints
1. **Level detection** — auto, verify on chart
2. **Trade plan** — user reviews before execution
3. **No auto-trading** — all decisions manual

## Push Right
Browser automation does the chart navigation and level marking. User only reviews the finished setup analysis.
