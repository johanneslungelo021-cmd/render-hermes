#!/usr/bin/env python3
"""
Pi Memory Web UI — Self-contained web interface for the persistent memory system.
Serves on http://0.0.0.0:8082

Usage:
  python3 memory-web.py            # Start server on :8082
  python3 memory-web.py --port 9090
  python3 memory-web.py --daemon   # Run in background
"""

import json
import os
import subprocess
import sys
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT = int(os.environ.get("MEMORY_WEB_PORT", 8082))
MEMORY_SCRIPT = Path("/root/pi/memory-tool/memory.py")
MEMORY_FILE = Path("/root/pi/COMPACTED_MEMORY.md")
INDEX_FILE = Path("/root/pi/memory-tool/sessions-index.json")


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🧠 Pi Memory</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
:root {
  --bg: #0d1117;
  --surface: #161b22;
  --border: #30363d;
  --text: #e6edf3;
  --text-dim: #8b949e;
  --accent: #58a6ff;
  --green: #3fb950;
  --red: #f85149;
  --yellow: #d29922;
  --radius: 8px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  padding: 0;
}
.topbar {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 12px 24px;
  display: flex;
  align-items: center;
  gap: 16px;
  position: sticky;
  top: 0;
  z-index: 100;
}
.topbar h1 { font-size: 18px; font-weight: 600; }
.topbar .status { font-size: 12px; color: var(--text-dim); margin-left: auto; }
.container { display: flex; height: calc(100vh - 50px); }
.sidebar {
  width: 280px;
  min-width: 280px;
  background: var(--surface);
  border-right: 1px solid var(--border);
  padding: 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.sidebar h2 { font-size: 13px; text-transform: uppercase; color: var(--text-dim); letter-spacing: 0.5px; }
.sidebar .section { margin-bottom: 8px; }
.sidebar .file-link {
  display: block;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text);
  text-decoration: none;
  cursor: pointer;
  background: transparent;
  border: none;
  width: 100%;
  text-align: left;
}
.sidebar .file-link:hover { background: rgba(88,166,255,0.1); color: var(--accent); }
.sidebar .file-link.active { background: rgba(88,166,255,0.15); color: var(--accent); }
.sidebar .file-link .size { float: right; color: var(--text-dim); font-size: 11px; }
.main {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px;
}
.main h1, .main h2, .main h3, .main h4 { margin-top: 1.5em; margin-bottom: 0.5em; }
.main h1 { font-size: 1.8em; border-bottom: 1px solid var(--border); padding-bottom: 0.3em; }
.main h2 { font-size: 1.4em; border-bottom: 1px solid var(--border); padding-bottom: 0.2em; }
.main h3 { font-size: 1.15em; }
.main p { margin-bottom: 1em; }
.main a { color: var(--accent); }
.main code {
  background: rgba(88,166,255,0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
}
.main pre {
  background: rgba(0,0,0,0.3);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  overflow-x: auto;
  margin-bottom: 1em;
}
.main pre code { background: none; padding: 0; }
.main table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 1em;
  font-size: 0.9em;
}
.main th, .main td {
  border: 1px solid var(--border);
  padding: 8px 12px;
  text-align: left;
}
.main th { background: var(--surface); font-weight: 600; }
.main tr:nth-child(even) { background: rgba(255,255,255,0.02); }
.main blockquote {
  border-left: 3px solid var(--accent);
  padding-left: 16px;
  color: var(--text-dim);
  margin-bottom: 1em;
}
.main ul, .main ol { padding-left: 24px; margin-bottom: 1em; }
.main li { margin-bottom: 0.3em; }
.main hr { border: none; border-top: 1px solid var(--border); margin: 1.5em 0; }
.search-box {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-size: 13px;
  outline: none;
}
.search-box:focus { border-color: var(--accent); }
.add-form { display: flex; gap: 8px; }
.add-form input {
  flex: 1;
  padding: 8px 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-size: 13px;
  outline: none;
}
.add-form input:focus { border-color: var(--green); }
.add-form button {
  padding: 8px 16px;
  background: var(--green);
  color: #000;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
}
.add-form button:hover { opacity: 0.85; }
.toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  background: var(--green);
  color: #000;
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  opacity: 0;
  transition: opacity 0.3s;
  z-index: 200;
}
.toast.show { opacity: 1; }
.loading { text-align: center; padding: 48px; color: var(--text-dim); }
@media (max-width: 768px) {
  .sidebar { display: none; }
  .container { flex-direction: column; }
  .main { padding: 16px; }
}
</style>
</head>
<body>
<div class="topbar">
  <h1>🧠 Pi Memory</h1>
  <div class="status" id="status">loading...</div>
</div>
<div class="container">
  <div class="sidebar" id="sidebar">
    <div class="section">
      <h2>Actions</h2>
      <form class="add-form" id="addForm">
        <input type="text" id="learningInput" placeholder="Add a learning..." required>
        <button type="submit">+</button>
      </form>
      <br>
      <input type="text" class="search-box" id="searchInput" placeholder="Search memory..." oninput="searchMemory(this.value)">
    </div>
    <div class="section">
      <h2>Sessions</h2>
      <div id="sessionList"></div>
    </div>
    <div class="section">
      <h2>Commands</h2>
      <button class="file-link" onclick="loadView('memory')">📄 Memory</button>
      <button class="file-link" onclick="loadView('learnings')">🧠 Learnings</button>
      <button class="file-link" onclick="loadView('sessions')">📊 Sessions</button>
      <button class="file-link" onclick="refresh()">🔄 Refresh</button>
    </div>
  </div>
  <div class="main" id="content">
    <div class="loading">Loading memory...</div>
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
const API = '/api';

async function api(path, opts = {}) {
  const res = await fetch(API + path, opts);
  return res.json();
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

async function refresh() {
  document.getElementById('content').innerHTML = '<div class="loading">Refreshing...</div>';
  await api('/save');
  loadView('memory');
  loadSidebar();
  showToast('Memory refreshed');
}

async function loadView(view) {
  const el = document.getElementById('content');
  el.innerHTML = '<div class="loading">Loading...</div>';
  
  if (view === 'memory') {
    const res = await fetch('/memory.md?' + Date.now());
    const md = await res.text();
    el.innerHTML = marked.parse(md);
    // Highlight current nav
    document.querySelectorAll('.file-link').forEach(b => b.classList.remove('active'));
  } else if (view === 'learnings') {
    const data = await api('/learnings');
    let html = '<h1>🧠 Learnings</h1>';
    if (data.learnings && data.learnings.length) {
      html += `<p>${data.learnings.length} learnings stored</p><ul>`;
      for (const l of data.learnings.slice().reverse()) {
        html += `<li>${l}</li>`;
      }
      html += '</ul>';
    } else {
      html += '<p>No learnings yet.</p>';
    }
    el.innerHTML = html;
  } else if (view === 'sessions') {
    const data = await api('/sessions');
    let html = '<h1>📊 Sessions</h1>';
    if (data.sessions && data.sessions.length) {
      html += `<p>${data.sessions.length} sessions indexed</p><ul>`;
      for (const s of data.sessions.slice().reverse()) {
        html += `<li><strong>${s.timestamp}</strong> (${s.size_kb}KB)</li>`;
      }
      html += '</ul>';
    } else {
      html += '<p>No sessions indexed.</p>';
    }
    el.innerHTML = html;
  }
}

async function loadSidebar() {
  const data = await api('/sessions');
  const el = document.getElementById('sessionList');
  if (data.sessions && data.sessions.length) {
    el.innerHTML = data.sessions.slice().reverse().map(s =>
      `<div class="file-link" onclick="loadView('memory')"><span>${s.timestamp.split(' ')[1] || s.timestamp}</span><span class="size">${s.size_kb}KB</span></div>`
    ).join('');
  } else {
    el.innerHTML = '<div style="color:var(--text-dim);font-size:13px">No sessions</div>';
  }
}

async function searchMemory(q) {
  if (!q || q.length < 2) { loadView('memory'); return; }
  const data = await api('/search?q=' + encodeURIComponent(q));
  const el = document.getElementById('content');
  if (data.results && data.results.length) {
    el.innerHTML = `<h1>🔍 Results for "${q}"</h1><p>${data.results.length} matches</p><ul>`
      + data.results.map(r => `<li><strong>${r.source}:${r.line}</strong> ${r.text}</li>`).join('')
      + '</ul>';
  } else {
    el.innerHTML = `<h1>🔍 No results for "${q}"</h1>`;
  }
}

document.getElementById('addForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = document.getElementById('learningInput');
  const text = input.value.trim();
  if (!text) return;
  const res = await api('/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text })
  });
  if (res.ok) {
    showToast('Learning added ✓');
    input.value = '';
    loadView('learnings');
  } else {
    showToast('Error: ' + (res.error || 'unknown'));
  }
});

// Init
(async () => {
  const data = await api('/status');
  document.getElementById('status').textContent = `${data.learnings} learnings · ${data.sessions} sessions · ${data.memory_lines} lines`;
  loadView('memory');
  loadSidebar();
})();
</script>
</body>
</html>
"""


class MemoryHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self.send_html(HTML)
        elif path == "/memory.md":
            self.send_file(MEMORY_FILE, "text/markdown")
        elif path == "/api/status":
            self.send_json(self.get_status())
        elif path == "/api/learnings":
            self.send_json(self.get_learnings())
        elif path == "/api/sessions":
            self.send_json(self.get_sessions())
        elif path == "/api/search":
            q = params.get("q", [""])[0]
            self.send_json(self.search(q))
        elif path == "/api/save":
            self.run_cmd([sys.executable, str(MEMORY_SCRIPT), "--save"])
            self.send_json({"ok": True})
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/add":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            text = body.get("text", "")
            if text:
                self.run_cmd([sys.executable, str(MEMORY_SCRIPT), "--add", text])
                self.send_json({"ok": True})
            else:
                self.send_json({"ok": False, "error": "empty text"})
        else:
            self.send_error(404)

    def send_html(self, content):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode() if isinstance(content, str) else content)

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def send_file(self, path, mime):
        if path.exists():
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.end_headers()
            self.wfile.write(path.read_bytes())
        else:
            self.send_error(404, f"{path.name} not found")

    def get_status(self):
        idx = self._load_index()
        mem = MEMORY_FILE.read_text().splitlines() if MEMORY_FILE.exists() else []
        return {
            "learnings": len(idx.get("learnings", [])),
            "sessions": len(idx.get("sessions", [])),
            "memory_lines": len(mem),
            "memory_chars": len("\n".join(mem)),
        }

    def get_learnings(self):
        idx = self._load_index()
        return {"learnings": idx.get("learnings", [])}

    def get_sessions(self):
        idx = self._load_index()
        return {"sessions": idx.get("sessions", [])}

    def search(self, q):
        results = []
        if MEMORY_FILE.exists():
            for i, line in enumerate(MEMORY_FILE.read_text().splitlines(), 1):
                if q.lower() in line.lower():
                    results.append({
                        "source": "COMPACTED_MEMORY.md",
                        "line": i,
                        "text": line.strip()[:200],
                    })
        idx = self._load_index()
        for l in idx.get("learnings", []):
            if q.lower() in l.lower():
                results.append({"source": "learnings", "line": 0, "text": l[:200]})
        return {"results": results[:30]}

    def _load_index(self):
        if INDEX_FILE.exists():
            try:
                return json.loads(INDEX_FILE.read_text())
            except Exception:
                pass
        return {"sessions": [], "learnings": []}

    def run_cmd(self, args):
        try:
            subprocess.run(args, capture_output=True, text=True, timeout=30)
        except Exception as e:
            print(f"cmd error: {e}")

    def log_message(self, fmt, *args):
        print(f"  [web] {args[0]} {args[1]} {args[2]}")


def main():
    global PORT
    daemon = False
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--port" and i + 1 < len(args):
            PORT = int(args[i + 1])
        elif a == "--daemon":
            daemon = True

    if daemon:
        pid = os.fork()
        if pid > 0:
            print(f"🧠 Pi Memory Web UI — PID {pid}")
            sys.exit(0)

    server = HTTPServer(("0.0.0.0", PORT), MemoryHandler)
    print(f"\n  🧠 Pi Memory Web UI")
    print(f"  ─────────────────")
    print(f"  Local:   http://localhost:{PORT}")
    print(f"  Network: http://0.0.0.0:{PORT}")
    print(f"  ─────────────────")
    print(f"  Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopping...")
        server.shutdown()


if __name__ == "__main__":
    main()
