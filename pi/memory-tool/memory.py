#!/usr/bin/env python3
"""
Pi Persistent Memory System
============================
Survives session resets. Call at session start to reload full context,
and at session end to persist what was learned.

Usage:
  python3 memory.py --load         # Print full memory (call at session start)
  python3 memory.py --save         # Capture current session state
  python3 memory.py --add "key=value"  # Add a memory entry
  python3 memory.py --search "query"   # Search memory
  python3 memory.py --compact      # Compact old session data
  python3 memory.py --status       # Quick summary
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

BASE = Path("/root/pi")
MEMORY_FILE = BASE / "COMPACTED_MEMORY.md"
INDEX_FILE = BASE / "memory-tool" / "sessions-index.json"
RAW_DIR = BASE / "memory-tool" / "raw"

# Also check agent-zero session memory and other key files
AGENT_ZERO_MEMORY = Path("/root/pi/agent-zero/SESSION_MEMORY.md")
AGENT_ZERO_DECISIONS = Path("/root/pi/agent-zero/DECISION_MAP.md")
PI_SESSIONS_DIR = Path("/root/.pi/agent/sessions/--root--")
EIGENT_MEMORY = Path("/root/eigent/SESSION_MEMORY.md")
WORKFLOWS_DIR = Path("/root/pi/agent-zero/workflows")
TRADER_INTEL_DIR = Path("/root/pi/agent-zero/trader-intelligence")

RAW_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────
#  MEMORY SCHEMA
# ─────────────────────────────────────────────────────

DEFAULT_MEMORY = """# 🧠 Pi Persistent Memory

**Last updated:** {date}
**Sessions indexed:** {session_count}

---

## 🏗️ Project Map

### Active Projects

| Project | Path | Status |
|---------|------|--------|
| Agent Zero (Remote) | `https://list-glucose-been-mil.trycloudflare.com` | ✅ Live v2.1 |
| Trader Intelligence | `/root/pi/agent-zero/trader-intelligence/` | ✅ Scanner + Schema |
| n8n Orchestrator | `https://rosimada.app.n8n.cloud` | ✅ Polling Round {round} |
| The Hidden Ledger | `/root/the-hidden-ledger/` | ✅ Numerai pipeline |
| Browser Stack | `/root/eigent/` + `:9222` | ✅ Chrome 149 |

### Key Credentials

| Service | Key (first 8 chars) | Location |
|---------|---------------------|----------|
| Mistral AI | `dU3kS44S...` | Agent Zero + .bashrc |
| Kaggle | `(stored)` | `/root/.kaggle/kaggle.json` |
| GitHub | `ghp_RE60O...` | `/root/.github-token` |
| OpenCode Zen | `sk-BYvG5n...` | `/root/.hermes/.env` |

---

## 📡 Infrastructure

| Component | Detail |
|-----------|--------|
| **Pi provider** | OpenCode / DeepSeek V4 Flash Free |
| **Agent Zero** | GCP Cloud Shell via Cloudflare tunnel |
| **LLM** | Mistral `mistral-large-latest` (128K ctx, vision) |
| **Browser** | Chrome 149, CDP on `:9222`, Xvfb stealth |
| **A0 CLI** | `/root/.venv/bin/a0` v2.1 |
| **n8n** | Cloud instance, polls Numerai every 15min |
| **Python venv** | `/root/the-hidden-ledger/.venv/` + `/root/.venv/` |

---

## 📋 Decision Map (Active Tickets)

| # | Ticket | Priority | Status |
|---|--------|----------|--------|
| 1 | **Numerai Agent Integration** | 🔴 High | ⏳ Pending |
| 2 | TradingView Browser Automation | 🔴 High | ✅ Done |
| 3 | **Workflow Orchestration** (n8n → swarm) | 🔴 High | ⏳ Pending |
| 4 | Data Storage & Brief Format | 🟡 Med | ✅ Schema done |
| 5 | **Fact-Checking Sources Audit** | 🟡 Med | ⏳ Pending |
| 6 | **SAIIA News Scraping** | 🟢 Low | ⏳ Pending |

---

## 🔧 Built & Proven

### Trader Intelligence Pipeline
- ✅ TradingView → Canvas capture → Mistral Vision → SMC JSON
- ✅ Ground-truth anchoring (DOM price fixes axis hallucination)
- ✅ Semantic inversion validator (Pydantic buy-below/sell-above rules)
- ✅ Multi-asset scanner (`scanner.py` — 8 assets in watchlist)
- ✅ Unified brief schema (`PipelineBrief` with SMC + Numerai + Macro + Gatekeeper)

### Known Fixes
- **Mistral API key**: The correct key is `dU3kS44S...` (first 8). The env var was set to a WRONG key `7iJPINtf...` — this was fixed in `.bashrc` during session 2026-06-30T02:25.
- **Responses API bug**: `a0_api_mode` must be `chat_completions` not `responses` for Mistral.
- **Axis hallucination**: Vision model misreads axis labels → DOM price anchor injects correct price.
- **Semantic inversion**: Pydantic `@model_validator` enforces buy-below/sell-above.

---

## 📜 Session Log

{history}

---

## 📁 Key File Locations

| Purpose | Path |
|---------|------|
| Pi session memory | `/root/.pi/agent/sessions/--root--/` |
| Agent Zero memory | `/root/pi/agent-zero/SESSION_MEMORY.md` |
| Decision map | `/root/pi/agent-zero/DECISION_MAP.md` |
| Trader scanner | `/root/pi/agent-zero/trader-intelligence/scanner.py` |
| Pydantic schema | `/root/pi/agent-zero/trader-intelligence/schema.py` |
| Workflow specs | `/root/pi/agent-zero/workflows/` |
| Numerai pipeline | `/root/the-hidden-ledger/run_numerai.sh` |
| Numerai model | `/root/the-hidden-ledger/ledger/numerai_model.py` |
| Numerai submission | `/root/the-hidden-ledger/ledger/numerai_pipeline.py` |
| Browser stack | `/root/eigent/` |
| n8n MCP config | `/root/.config/opencode/opencode.json` |
| Moltcorp agent | `/root/moltcorp-agent/index.mjs` |
| Kaggle config | `/root/.kaggle/kaggle.json` |
| GitHub token | `/root/.github-token` |
| pi settings | `/root/.pi/agent/settings.json` |
| Mistral key (bashrc) | `/root/.bashrc` |

---

## 🧠 Recent Decisions & Learnings

{learnings}
"""


# ─────────────────────────────────────────────────────
#  CORE FUNCTIONS
# ─────────────────────────────────────────────────────


def load_index() -> dict:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text())
        except Exception:
            pass
    return {"sessions": [], "learnings": [], "last_round": 0}


def save_index(index: dict):
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(index, indent=2))


def scan_pi_sessions() -> list:
    """Index all pi session files with metadata."""
    sessions = []
    if not PI_SESSIONS_DIR.exists():
        return sessions
    for f in sorted(PI_SESSIONS_DIR.glob("*.jsonl")):
        size = f.stat().st_size
        # Parse timestamp from filename
        m = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})", f.name)
        ts = m.group(1).replace("-", ":").replace("T", " ").replace("--", "-") if m else "unknown"
        sessions.append({
            "file": str(f),
            "name": f.name,
            "size": size,
            "size_kb": round(size / 1024, 1),
            "timestamp": ts,
        })
    return sessions


def extract_session_summary(path: str) -> str:
    """Extract key decisions and actions from a pi session JSONL."""
    try:
        with open(path) as f:
            lines = f.readlines()
    except Exception:
        return ""

    key_events = []
    user_messages = []
    
    for line in lines:
        try:
            obj = json.loads(line.strip())
        except Exception:
            continue
        
        if obj.get("type") != "message":
            continue
        
        msg = obj.get("message", {})
        role = msg.get("role")
        
        if role == "user":
            content = msg.get("content", [])
            if isinstance(content, list) and content:
                text = content[0].get("text", "")
                # Skip very short messages and navigation commands
                if len(text) > 15 and not text.startswith("read ") and not text.startswith("ls "):
                    user_messages.append(text[:150])
        elif role == "assistant":
            content = msg.get("content", [])
            o = msg.get("output", "")
            # Check for tool calls that indicate action
            for c in content:
                if c.get("type") == "toolCall":
                    name = c.get("name", "")
                    args = c.get("arguments", {})
                    if name == "write":
                        key_events.append(f"📝 Wrote: {args.get('path', '?')}")
                    elif name == "edit":
                        key_events.append(f"✏️ Edited: {args.get('path', '?')}")
                    elif name == "bash":
                        cmd = args.get("command", "")[:120]
                        if any(kw in cmd for kw in ["pip install", "npm install", "a0 ", "curl "]):
                            key_events.append(f"💻 CMD: {cmd[:120]}")
    
    summary = []
    for u in user_messages[:5]:
        summary.append(f"  User: {u}")
    for e in key_events[:8]:
        summary.append(f"  {e}")
    
    return "\n".join(summary)


def get_numerai_round() -> int:
    """Try to get current Numerai round from state or API."""
    state_file = Path("/root/the-hidden-ledger/.round_state.json")
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text())
            return data.get("last_round_processed", 0)
        except Exception:
            pass
    return 0


def build_memory() -> str:
    """Build the complete memory file."""
    index = load_index()
    sessions = scan_pi_sessions()
    
    # Update session index
    known_files = {s["file"] for s in index.get("sessions", [])}
    for s in sessions:
        if s["file"] not in known_files:
            summary = extract_session_summary(s["file"])
            if summary:
                s["summary"] = summary
            index["sessions"].append(s)
    
    # Build history section
    recent_sessions = sorted(index["sessions"], key=lambda x: x.get("timestamp", ""), reverse=True)[:10]
    history_lines = []
    for i, s in enumerate(recent_sessions):
        ts = s.get("timestamp", "?")
        size = s.get("size_kb", 0)
        name = s.get("name", "?")[:50]
        summary = s.get("summary", "")
        history_lines.append(f"### Session {i+1}: {ts} ({size}KB)")
        if summary:
            history_lines.append(summary)
        history_lines.append("")
    
    history = "\n".join(history_lines[:80]) if history_lines else "*(no sessions yet)*"
    
    # Build learnings section
    learnings = index.get("learnings", [])
    learnings_str = "\n".join(f"- {l}" for l in learnings[-20:]) if learnings else "*(none recorded)*"
    
    round_num = get_numerai_round() or index.get("last_round", 0)
    
    memory = DEFAULT_MEMORY.format(
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        session_count=len(index["sessions"]),
        round=round_num,
        history=history,
        learnings=learnings_str,
    )
    
    return memory


def load_memory():
    """Print the full memory for loading into a new session."""
    if not MEMORY_FILE.exists():
        memory = build_memory()
        MEMORY_FILE.write_text(memory)
    content = MEMORY_FILE.read_text()
    print(content)


def save_memory():
    """Rebuild and save the memory file."""
    memory = build_memory()
    MEMORY_FILE.write_text(memory)
    print(f"✅ Memory saved to {MEMORY_FILE}")
    print(f"   Size: {len(memory)} chars / {len(memory.splitlines())} lines")


def add_learning(entry: str):
    """Add a new learning/decision to persistent memory."""
    index = load_index()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    index.setdefault("learnings", []).append(f"[{timestamp}] {entry}")
    save_index(index)
    save_memory()
    print(f"✅ Learning added: {entry}")


def search_memory(query: str):
    """Search all memory data."""
    results = []
    # Search compacted memory
    if MEMORY_FILE.exists():
        content = MEMORY_FILE.read_text()
        for i, line in enumerate(content.splitlines(), 1):
            if query.lower() in line.lower():
                results.append(("COMPACTED_MEMORY.md", i, line.strip()[:150]))
    
    # Search index learnings
    index = load_index()
    for l in index.get("learnings", []):
        if query.lower() in l.lower():
            results.append(("learnings", 0, l[:150]))
    
    if results:
        print(f"🔍 Found {len(results)} results for '{query}':\n")
        for src, line, text in results[:20]:
            print(f"  [{src}:{line}] {text}")
    else:
        print(f"No results for '{query}'")


def compact():
    """Compact old sessions and rebuild memory."""
    index = load_index()
    
    # Keep only session metadata, remove detailed summaries for old sessions
    sessions = index.get("sessions", [])
    for s in sessions[:-5]:  # Keep summaries for last 5, compact older
        if "summary" in s:
            del s["summary"]
    
    save_index(index)
    save_memory()
    print(f"✅ Compacted {len(sessions)} sessions")
    print(f"   Keeping {min(5, len(sessions))} detailed summaries")


def status():
    """Quick status overview."""
    index = load_index()
    sessions = index.get("sessions", [])
    learnings = index.get("learnings", [])
    
    pi_sessions = list(PI_SESSIONS_DIR.glob("*.jsonl")) if PI_SESSIONS_DIR.exists() else []
    
    print(f"🧠 Pi Persistent Memory")
    print(f"═" * 40)
    print(f"  Sessions indexed:  {len(sessions)}")
    print(f"  Pi session files:  {len(pi_sessions)}")
    print(f"  Learnings stored:  {len(learnings)}")
    print(f"  Last round:        {get_numerai_round()}")
    print(f"  Memory file:       {MEMORY_FILE}")
    if MEMORY_FILE.exists():
        print(f"  Memory size:       {len(MEMORY_FILE.read_text().splitlines())} lines")
    print(f"")
    print(f"  Recent sessions:")
    for s in sorted(sessions, key=lambda x: x.get("timestamp", ""), reverse=True)[:5]:
        print(f"    {s.get('timestamp','?'):25s} {s.get('size_kb',0):>8.1f}KB")
    print(f"")
    print(f"  Recent learnings:")
    for l in learnings[-5:]:
        print(f"    {l[:120]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "--load":
        load_memory()
    elif cmd == "--save":
        save_memory()
    elif cmd == "--add" and len(sys.argv) > 2:
        add_learning(" ".join(sys.argv[2:]))
    elif cmd == "--search" and len(sys.argv) > 2:
        search_memory(" ".join(sys.argv[2:]))
    elif cmd == "--compact":
        compact()
    elif cmd == "--status":
        status()
    elif cmd == "--rebuild":
        save_memory()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
