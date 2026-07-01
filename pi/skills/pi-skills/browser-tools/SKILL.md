---
name: browser-tools
description: Full web browser automation via Chrome DevTools Protocol (CDP) — launch, navigate, search, scrape, intercept, and publish with a real Chromium instance.
---

# Eigent Browser Stack

Eigent gives your agent stack **hands and eyes** on the raw, uncooperative web.
It drives a real Chromium instance through the Chrome DevTools Protocol (CDP).

## Files

- `browser-start.js` — Launch Chromium, wire up user profile, wait for CDP
- `browser-intercept.js` — Race-condition-free network idle detection
- `browser-search.js` — Live web search via real browser (try/finally safe)
- `browser-navigate.js` — Navigate + capture: text, HTML, or both
- `mcp-server.js` — MCP server exposing all tools via stdio transport

## Architectural Decisions

### 1. Network Idle Detection — Race Condition Fix
SPAs fire requests in bursts separated by brief gaps (5–50ms). `requestWillBeSent` clears the idle timer every time fresh activity starts. A secondary guard in the timer callback re-checks inflight count before resolving.

### 2. Connection Cleanup — Ghost Process Fix
All risky code lives in try/finally. Teardown (`client.close()`, `proc.kill()`) runs regardless of how the try block exits.

### 3. Profile Support
The `--profile` flag copies Chrome user data into an isolated temp dir. Source is never mutated. Temp dir is deleted by `stopBrowser()`.

## Usage

Start/stop:
```js
const { startBrowser, stopBrowser } = require('./browser-start');
const handle = await startBrowser({ headless: true, profile: 'Default', port: 9222 });
stopBrowser(handle);
```

Search:
```js
const { browserSearch } = require('./browser-search');
const results = await browserSearch({ query: 'XRPL validators', engine: 'duckduckgo' });
```

Navigate and capture:
```js
const { navigatePage } = require('./browser-navigate');
const page = await navigatePage({ url: 'https://example.com', extractMode: 'text' });
```

Network idle detection:
```js
const { enableNetworkTracking, waitForNetworkIdle } = require('./browser-intercept');
await enableNetworkTracking(client);
await Page.navigate({ url });
const { requestCount, durationMs } = await waitForNetworkIdle(client, { idleMs: 500 });
```

## Binary Discovery Order
1. `/opt/google/chrome/chrome` (Cloud Shell / Claude sandbox)
2. `/usr/bin/google-chrome` / `google-chrome-stable`
3. `/usr/bin/chromium` / `chromium-browser`
4. `/snap/bin/chromium`
5. `~/.cache/puppeteer/.../chrome`
6. `$PATH` lookup

## Known Limitations
- No MFA automation
- `--headless=new` (Chrome 112+) needs no display server
- Google selectors drift frequently; DuckDuckGo HTML endpoint is most stable
- Temp dir names use 48 bits of entropy — collisions extremely unlikely
