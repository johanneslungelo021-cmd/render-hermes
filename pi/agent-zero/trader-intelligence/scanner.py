#!/usr/bin/env python3
"""
Trader Intelligence System — Multi-Asset Scanner

Cycles through a watchlist, for each asset:
  1. Navigates TradingView via CDP (stealth Chrome)
  2. Extracts live price anchor from DOM title
  3. Captures chart canvas as PNG
  4. Sends to Mistral vision for SMC analysis
  5. Validates output through Pydantic schema
  6. Appends to consolidated brief

Usage:
  python3 scanner.py
  python3 scanner.py --watchlist BTCUSD,XAUUSD
  python3 scanner.py --dry-run
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from schema import (
    AssetAnalysis,
    AuditStep,
    GatekeeperDecision,
    MacroContext,
    NumeraiSignals,
    PipelineBrief,
    SMCPatterns,
)

# ── Configuration ──────────────────────────────────────

WATCHLIST = [
    "FX:EURUSD",
    "FX:GBPUSD",
    "BTCUSD",
    "XAUUSD",
    "SP:SPX",
    "NASDAQ:TSLA",
    "FX:USDJPY",
    "COINBASE:ETHUSD",
]

CHART_URL = "https://www.tradingview.com/chart/?symbol="
CDP_PORT = 9222
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
MISTRAL_MODEL = "pixtral-12b"
OUTPUT_DIR = Path("/root/pi/agent-zero/trader-intelligence/scans")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CAPTURE_CANVAS_SCRIPT = """
(() => {
    const canvases = document.querySelectorAll('canvas');
    if (canvases.length === 0) return null;
    let best = canvases[0];
    for (const c of canvases) {
        if (c.width * c.height > best.width * best.height) best = c;
    }
    return best.toDataURL('image/png');
})()
"""


# ── CDP Helpers ────────────────────────────────────────


def _run_node(js_code: str, timeout: int = 30) -> Tuple[int, str, str]:
    """Run a Node.js script with chrome-remote-interface available."""
    proc = subprocess.run(
        ["node", "-e", js_code],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd="/root/eigent",
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()[:300]


def cdp_eval(script: str, timeout: int = 30) -> Optional[str]:
    """Evaluate JS in Chrome via CDP, return console.log'd JSON value."""
    js = (
        "const CDP = require('chrome-remote-interface');\n"
        "(async () => {\n"
        "  let client;\n"
        "  try {\n"
        f"    client = await CDP({ json.dumps({'port': CDP_PORT}) });\n"
        "    const { Page, Runtime } = client;\n"
        "    await Page.enable();\n"
        "    const r = await Runtime.evaluate({\n"
        f"      expression: {json.dumps(script)},\n"
        "      returnByValue: true\n"
        "    });\n"
        "    if (r.result.value !== null && r.result.value !== undefined)\n"
        "      console.log(JSON.stringify(r.result.value));\n"
        "  } finally {\n"
        "    if (client) await client.close();\n"
        "  }\n"
        "})().catch(e => { console.error(e.message); process.exit(1); });\n"
    )
    rc, out, err = _run_node(js, timeout)
    if rc != 0 and err:
        print(f"  [CDP] {err[:150]}")
    return out or None


def cdp_navigate(url: str, wait_s: int = 18) -> bool:
    """Navigate Chrome to url and wait for page load."""
    js = (
        "const CDP = require('chrome-remote-interface');\n"
        "(async () => {\n"
        "  let client;\n"
        "  try {\n"
        f"    client = await CDP({ json.dumps({'port': CDP_PORT}) });\n"
        "    const { Page } = client;\n"
        "    await Page.enable();\n"
        f"    await Page.navigate({ json.dumps({'url': url}) });\n"
        f"    await new Promise(r => setTimeout(r, {wait_s * 1000}));\n"
        "    console.log('OK');\n"
        "  } finally {\n"
        "    if (client) await client.close();\n"
        "  }\n"
        "})().catch(e => { console.error(e.message); process.exit(1); });\n"
    )
    rc, out, err = _run_node(js, wait_s + 10)
    return "OK" in out


# ── Price Anchor Extraction ────────────────────────────


def parse_price(title: str) -> Tuple[Optional[str], Optional[float]]:
    """Parse 'EURUSD 1.14020 -0.18%' into (asset, price)."""
    for pat in [
        r"^([A-Za-z0-9:._/-]+)\s+([0-9,.]+)",
    ]:
        m = re.match(pat, title)
        if m:
            try:
                return m.group(1), float(m.group(2).replace(",", ""))
            except ValueError:
                pass
    return None, None


# ── Mistral Vision ─────────────────────────────────────


def mistral_analyze(
    ticker: str, price: Optional[float], b64_png: str
) -> Optional[dict]:
    """Send chart canvas to Mistral, return parsed SMC JSON."""
    if not b64_png:
        return None

    anchor = (
        f"CRITICAL: The asset is {ticker}. "
        f"The current market price at the FAR RIGHT edge is exactly {price}. "
        f"Use this as your absolute price anchor."
        if price
        else ""
    )

    prompt = (
        f"{anchor}\n\n"
        f"Analyze this {ticker} chart for Smart Money Concepts (SMC).\n"
        f"Return ONLY valid JSON:\n"
        '{"order_blocks": {"buy": [], "sell": []}, '
        '"fvg": [], "liquidity_sweeps": [], '
        '"choch": [], "bos": [], '
        '"support": [], "resistance": [], '
        '"structure": "bullish|bearish|neutral"}\n\n'
        f"SMC RULES:\n"
        f"- Buy OBs MUST be below {price}\n"
        f"- Sell OBs MUST be above {price}\n"
        f"- Support below {price}, Resistance above {price}"
    )

    try:
        resp = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {MISTRAL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MISTRAL_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": f"data:image/png;base64,{b64_png}",
                            },
                        ],
                    }
                ],
                "max_tokens": 1500,
                "temperature": 0.1,
            },
            timeout=35,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

        # Strip markdown fences
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
        if m:
            content = m.group(1)

        result = json.loads(content)
        n_buy = len(result.get("order_blocks", {}).get("buy", []))
        n_sell = len(result.get("order_blocks", {}).get("sell", []))
        print(f"   -> Vision OK ({n_buy} buy OB, {n_sell} sell OB)")
        return result

    except Exception as e:
        print(f"   -> Vision error: {e}")
        return None


# ── SMC Boundary Check (inline, no Pydantic context) ──


def check_smc_boundaries(
    smc: dict, price: Optional[float]
) -> Optional[str]:
    """Return error string if SMC boundaries violated, else None."""
    if price is None:
        return None
    for label, levels, should_be_above in [
        ("Buy OB", smc.get("order_blocks", {}).get("buy", []), False),
        ("Sell OB", smc.get("order_blocks", {}).get("sell", []), True),
        ("Support", smc.get("support", []), False),
        ("Resistance", smc.get("resistance", []), True),
    ]:
        for lvl in levels:
            if should_be_above and lvl < price:
                return f"SMC Violation: {label} {lvl} below price {price}"
            if not should_be_above and lvl > price:
                return f"SMC Violation: {label} {lvl} above price {price}"
    return None


# ── Per-Asset Scan ─────────────────────────────────────


@dataclass
class ScanResult:
    ticker: str
    current_price: Optional[float]
    screenshot_path: Optional[Path]
    raw_title: str
    smc_json: Optional[dict]
    validation_error: Optional[str]
    duration_ms: int
    success: bool = False


def scan_one(ticker: str) -> ScanResult:
    t0 = time.time()
    url = CHART_URL + ticker
    print(f"\n  >>> {ticker}")

    # 1. Navigate
    if not cdp_navigate(url):
        return ScanResult(ticker, None, None, "", None, "nav fail", 0)

    # 2. Price anchor
    raw = cdp_eval("document.title")
    title = json.loads(raw) if raw else ""
    _, price = parse_price(title or "")
    print(f"  Price: {price}  |  Title: {title[:60]}")

    # 3. Canvas
    raw_canvas = cdp_eval(CAPTURE_CANVAS_SCRIPT)
    b64 = (json.loads(raw_canvas) or "").split(",", 1)[-1] if raw_canvas else ""
    if not b64:
        return ScanResult(ticker, price, None, title or "", None, "no canvas", int((time.time()-t0)*1000))

    safe = ticker.replace(":", "_")
    shot = OUTPUT_DIR / f"{safe}_{int(t0)}.png"
    shot.write_bytes(base64.b64decode(b64))
    print(f"  Canvas: {shot.name} ({shot.stat().st_size}B)")

    # 4. Mistral
    smc = mistral_analyze(ticker, price, b64)
    if not smc:
        return ScanResult(ticker, price, shot, title or "", None, "vision fail", int((time.time()-t0)*1000))

    # 5. Validate
    err = check_smc_boundaries(smc, price)
    if err:
        print(f"  !! {err}")
    else:
        print(f"  OK")

    return ScanResult(
        ticker=ticker,
        current_price=price,
        screenshot_path=shot,
        raw_title=title or "",
        smc_json=smc,
        validation_error=err,
        duration_ms=int((time.time() - t0) * 1000),
        success=err is None,
    )


# ── Pipeline ───────────────────────────────────────────


def run(watchlist: List[str]) -> PipelineBrief:
    bid = f"brief-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    brief = PipelineBrief(brief_id=bid)
    print(f"\n{'='*60}")
    print(f"  TRADER INTELLIGENCE SCANNER  |  {len(watchlist)} assets")
    print(f"{'='*60}")

    results = []
    for ticker in watchlist:
        r = scan_one(ticker)
        results.append(r)
        if r.success and r.smc_json:
            try:
                smc = SMCPatterns(**r.smc_json)
                brief.assets.append(
                    AssetAnalysis(
                        ticker=ticker,
                        current_price=r.current_price or 0.0,
                        screenshot_path=str(r.screenshot_path) if r.screenshot_path else None,
                        smc=smc,
                    )
                )
                brief.add_audit_step("vision", True, ticker, duration_ms=r.duration_ms)
            except Exception as e:
                brief.add_audit_step("vision", False, ticker, error=str(e))
        else:
            brief.add_audit_step("vision", False, ticker, error=r.validation_error or "fail")

    passed = sum(1 for r in results if r.success)
    print(f"\n  Done: {passed}/{len(watchlist)} passed")
    path = OUTPUT_DIR / f"{bid}.json"
    path.write_text(brief.to_json())
    print(f"  Brief: {path}")
    return brief


def main():
    wl = WATCHLIST
    if len(sys.argv) > 1 and sys.argv[1] == "--dry-run":
        url = CHART_URL + wl[0]
        ok = cdp_navigate(url, 12)
        print(f"  Navigate {wl[0]}: {'OK' if ok else 'FAIL'}")
        if ok:
            raw = cdp_eval("document.title")
            print(f"  Title: {raw}")
        return
    if len(sys.argv) > 2 and sys.argv[1] == "--watchlist":
        wl = [s.strip() for s in sys.argv[2].split(",") if s.strip()]
    run(wl)


if __name__ == "__main__":
    main()

