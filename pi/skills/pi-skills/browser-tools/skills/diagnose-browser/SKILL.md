# Diagnose Browser Failures

Five failure categories with runnable one-liners:

1. **Chrome not running** — `browser_start()` or `/root/.pi/agent/skills/pi-skills/browser-tools/browser-start.js`
2. **CDP timeout** — Check `curl -s http://127.0.0.1:9222/json/version`. If dead, restart Chrome.
3. **Selector not found** — Run `browser_eval(code: "document.querySelector('...')")` to test. Use snapshot/aria refs over CSS.
4. **Bot detection** — Restart with Xvfb: `browser_start(xvfb: true)`. Stealth plugin patches 20+ signals.
5. **Network blocked** — Check `browser_intercept()` for 403/429. Add delay or rotate UA.
