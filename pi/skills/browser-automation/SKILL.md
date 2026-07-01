---
name: browser-automation
description: Full-stack browser automation via pi-browser-tools MCP server + opencode plugin. 12 tools exposed as MCP tools, plus 5 native plugin tools with lifecycle hooks. Use for web scraping, form filling, OAuth login, API reverse-engineering, and visual testing.
---

# Browser Automation Stack

## Architecture

```
opencode (binary)
  ├── MCP client → browser MCP server (12 tools)
  │                 - nav, content, eval, cookies, screenshot
  │                 - select, intercept, watch, search, pick, hn-scraper
  │                 - browser_start (with --xvfb for non-headless mode)
  ├── Plugin → PiPlugin (5 native tools + lifecycle hooks)
  │              - browser_ensure, browser_type, browser_click
  │              - credential_get, page_state
  │              - tool.execute.before (auto-starts Chrome)
  │              - shell.env (injects XVFB_ENABLED)
  ├── Supabase MCP (remote) — DB, functions, auth
  └── Redis Cloud — persistent key-value state
```

## Planning Before Automation

Before running browser automation, plan with the `/grill` command:

```
/grill scrape hacker news front page for top stories
```

This uses opencode's own model to walk through 8 canonical questions and
produce a structured **TaskSpec** (JSON) that can be fed to `browser_scrape`
or `browser_publish`. No external API key needed.

For quick local exploration, the MCP `agent_grill` tool returns an unresolved
spec with the 8 questions as prompts:

- `agent_grill(description: "...")` — unresolved spec with prompts to fill
- `agent_grill(answers: {...})` — builds a validated TaskSpec from structured answers
- `agent_grill(validate: "...")` — validates an existing TaskSpec
- `agent_grill(questions: true)` — lists the 8 grilling questions

Example answers object:
```json
{
  "intent": "Scrape HN front page for top 30 stories",
  "actionType": "scrape",
  "targetUrl": "https://news.ycombinator.com",
  "idleMs": 600,
  "successCriteria": ["title list contains >= 30 items"],
  "failureModes": ["HN rate limiting", "lazy-loaded content"],
  "schema": {
    "title": { "selector": "td.title a" },
    "link": { "type": "attr", "selector": "td.title a", "attr": "href" }
  }
}
```

## Getting Started

### Start Chrome (if not running)
```bash
node /root/.pi/agent/skills/pi-skills/browser-tools/browser-start.js
# Or with Xvfb non-headless mode (bypasses bot detection):
Xvfb :99 -screen 0 1920x1080x24 &
DISPLAY=:99 node /root/.pi/agent/skills/pi-skills/browser-tools/browser-start.js
# Or with profile (copies Chrome cookies/logins):
node /root/.pi/agent/skills/pi-skills/browser-tools/browser-start.js --profile
```

> The `browser_ensure` plugin tool does this automatically. If Chrome isn't running when a browser tool is called, the plugin's `tool.execute.before` hook starts it — including Xvfb if available.

### Available MCP Tools (15)
All accessible as MCP tools named `browser_*`:

| Tool | Function | Key Args |
|------|----------|----------|
| `browser_start` | Launch Chrome + Xvfb | `profile`(bool), `xvfb`(bool) |
| `browser_nav` | Navigate to URL | `url`, `new_tab`, `reload` |
| `browser_content` | Extract Markdown | `url` |
| `browser_eval` | Run JS in page | `code` |
| `browser_cookies` | Dump cookies | — |
| `browser_screenshot` | PNG screenshot | `selector` |
| `browser_select` | CSS → structured data | `selector` |
| `browser_intercept` | Capture API responses | `url`, `filter`, `timeout_ms` |
| `browser_watch` | Watch DOM mutations | `url`, `selector`, `duration_ms` |
| `browser_search` | Bing search | `query` |
| `browser_hn_scraper` | HN front page | `limit` |
| `browser_pick` | Interactive picker | `message` |
| `browser_scrape` | Schema-driven extraction | `url?`, `schema`, `assert`(bool) |
| `browser_publish` | Action sequence runner | `actions`, `verbose`(bool) |
| `agent_grill` | TaskSpec generator | `description`, `answers`, `validate`, `questions` |

### Plugin Tools (5 native + 2 lifecycle hooks)
| Tool | Function |
|------|----------|
| `browser_ensure` | Ensure Chrome + Xvfb running (auto-started in `tool.execute.before`) |
| `browser_type` | Type into React/SPA inputs via CDP `Input.insertText` |
| `browser_click` | Click element with CDP `Input.dispatchMouseEvent` |
| `credential_get` | Get stored credential from vault |
| `page_state` | Full page snapshot (title, URL, text) |

## Bot Detection Bypass

The stack defeats bot detection at 3 levels:
1. **Stealth plugin** (puppeteer-extra-plugin-stealth) — patches 20+ fingerprint signals
2. **Xvfb virtual display** — Chrome runs non-headless, no `--headless` flag
3. **CDP Input.insertText** — types into React controlled components properly

Approach for blocked login forms:
1. Start browser with Xvfb: `browser_start(xvfb: true)`
2. Navigate to login page
3. Focus fields via JS, then use `browser_type` (CDP Input.insertText)
4. Click submit via `browser_click` (native MouseEvent)

## Credential Vault

Stored in `/root/.pi/agent/auth.json`. Retrieve with `credential_get(key)`.

## State Persistence

Use Redis Cloud for cross-session state: `redis_state(action, key, value?)`
