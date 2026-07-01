# Session Memory — Browser Tools

## Chrome Binary
- **Binary**: `/root/.cache/ms-playwright/chromium-1228/chrome-linux/chrome` (Chromium 149)
- **Discovery**: Added Playwright path first in `CHROME_CANDIDATES` to avoid broken snap wrapper
- **Snap wrapper** `/usr/bin/chromium-browser` moved to last resort (requires snap, not installed)

## Usage
```
const { startBrowser } = require('./browser-start');
const h = await startBrowser({ headless: true, port: 9236 });
// Chrome starts on :9236
```

## Teardown Lifecycle

See [TEARDOWN_LIFECYCLE.md](./TEARDOWN_LIFECYCLE.md) for the full 4-step browser teardown chain:

| Step | What | Why |
|------|------|-----|
| 1 | `Browser.close` via CDP | Flushes cookies, IndexedDB, localStorage to disk before anything dies |
| 2 | PID tree `SIGTERM` → `SIGKILL` fallback | Kills browser + all children (GPU, renderers, network) in order |
| 3 | Xvfb socket cleanup (`/tmp/.X10-lock`) | Prevents display-port exhaustion across NATS worker pool |
| 4 | `try/finally` + `process.on('SIGINT'/'SIGTERM'/'exit')` | Guarantees teardown runs even on catastrophic failure |

## Clean vs Dirty Closure

| Metric | Clean Shutdown | Dirty Shutdown |
|--------|---------------|----------------|
| Session State | Flushed to disk, persistent | Lost or corrupted |
| Profile Integrity | Safe for `fs.cpSync` | Lock warnings next launch |
| Resources | Processes cleared, sockets released | Zombie processes, /tmp leaks |
| Reusability | Immediate lease | Blocks on file/display locks |
