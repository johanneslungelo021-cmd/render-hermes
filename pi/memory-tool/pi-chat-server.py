#!/usr/bin/env python3
"""
Pi Chat Server
==============
A web chat interface for pi, wrapping `pi --mode rpc` into a browser UI.
Streams responses via SSE so you can chat with the AI from your browser.

Usage:
  python3 pi-chat-server.py [--port 8085] [--memory-web http://localhost:8083]
"""

import json
import os
import subprocess
import sys
import threading
import time
import uuid
import urllib.parse
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from queue import Queue, Empty

PORT = int(os.environ.get("PI_CHAT_PORT", 8085))
MEMORY_WEB_URL = os.environ.get("MEMORY_WEB_URL", "http://localhost:8083")
A2A_URL = os.environ.get("A2A_URL", "http://localhost:8084")

# ── Pi RPC Process Management ────────────────────────

class PiRPC:
    """Manages a `pi --mode rpc` subprocess for chat interactions."""

    def __init__(self):
        self.proc = None
        self.lock = threading.Lock()
        self.event_queues = {}
        self.buffer = ""
        self.running = False
        self.reader_thread = None

    def start(self):
        with self.lock:
            if self.running:
                return True
            
            try:
                self.proc = subprocess.Popen(
                    ["pi", "--mode", "rpc", "--no-session"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=0,
                )
                self.running = True
                
                # Start reader thread
                self.reader_thread = threading.Thread(target=self._read_loop, daemon=True)
                self.reader_thread.start()
                
                print(f"  [PiRPC] Started pi --mode rpc (PID {self.proc.pid})")
                return True
            except Exception as e:
                print(f"  [PiRPC] Failed to start: {e}")
                return False

    def _read_loop(self):
        partial = ""
        while self.running and self.proc:
            try:
                chunk = self.proc.stdout.read(1)
                if not chunk:
                    break
                partial += chunk
                if chunk == "\n":
                    line = partial.strip()
                    if line:
                        self._dispatch(line)
                    partial = ""
            except Exception:
                break
        
        # Process any remaining data
        if partial.strip():
            self._dispatch(partial.strip())
        
        self.running = False

    def _dispatch(self, line):
        try:
            event = json.loads(line)
            ev_type = event.get("type")
            
            # Route to matching queues
            to_remove = []
            for qid, (q, filter_fn) in self.event_queues.items():
                if filter_fn(event):
                    q.put(event)
                    if ev_type in ("agent_end", "response") and event.get("command") != "message_update":
                        to_remove.append(qid)
            
            for qid in to_remove:
                self.event_queues.pop(qid, None)
                
        except json.JSONDecodeError:
            pass

    def send_command(self, cmd: dict) -> bool:
        with self.lock:
            if not self.running or not self.proc:
                return False
            line = json.dumps(cmd) + "\n"
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
            return True

    def register_queue(self, qid: str, filter_fn=None):
        if filter_fn is None:
            filter_fn = lambda e: True
        self.event_queues[qid] = (Queue(), filter_fn)

    def unregister_queue(self, qid: str):
        self.event_queues.pop(qid, None)

    def get_queue(self, qid: str):
        entry = self.event_queues.get(qid)
        return entry[0] if entry else None

    def stop(self):
        with self.lock:
            self.running = False
            if self.proc:
                try:
                    self.send_command({"type": "abort"})
                    self.proc.stdin.close()
                    self.proc.terminate()
                    self.proc.wait(timeout=5)
                except Exception:
                    self.proc.kill()
                self.proc = None


# ── Global Pi RPC Instance ───────────────────────────

pi_rpc = PiRPC()


# ── Chat Sessions ────────────────────────────────────

class ChatSession:
    """Tracks a browser chat session."""

    def __init__(self, sid: str):
        self.id = sid
        self.messages = []
        self.created = datetime.now(timezone.utc).isoformat()
        self.last_active = time.time()

    def add_message(self, role: str, content: str):
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.last_active = time.time()

    def to_dict(self):
        return {
            "id": self.id,
            "messages": self.messages,
            "created": self.created,
        }


sessions: dict[str, ChatSession] = {}


def get_or_create_session(sid: str) -> ChatSession:
    if sid not in sessions:
        sessions[sid] = ChatSession(sid)
    return sessions[sid]


# ── HTML Template ────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pi Chat</title>
<style>
  :root {
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-tertiary: #21262d;
    --text-primary: #e6edf3;
    --text-secondary: #8b949e;
    --text-muted: #484f58;
    --accent: #58a6ff;
    --accent-hover: #79c0ff;
    --border: #30363d;
    --success: #3fb950;
    --warning: #d29922;
    --error: #f85149;
    --user-msg: #1f2937;
    --assistant-msg: #161b22;
    --code-bg: #0d1117;
    --sidebar-width: 280px;
    --header-height: 56px;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    display: flex;
    height: 100vh;
    overflow: hidden;
  }

  /* ── Sidebar ── */
  .sidebar {
    width: var(--sidebar-width);
    background: var(--bg-secondary);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
  }

  .sidebar-header {
    padding: 16px;
    border-bottom: 1px solid var(--border);
  }

  .sidebar-header h2 {
    font-size: 16px;
    color: var(--text-primary);
    margin-bottom: 4px;
  }

  .sidebar-header p {
    font-size: 12px;
    color: var(--text-secondary);
  }

  .memory-panel {
    padding: 12px;
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .memory-stat {
    background: var(--bg-tertiary);
    border-radius: 6px;
    padding: 10px 12px;
    font-size: 13px;
  }

  .memory-stat .label {
    color: var(--text-secondary);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .memory-stat .value {
    color: var(--accent);
    font-size: 14px;
    font-weight: 600;
    margin-top: 2px;
  }

  .service-link {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    border-radius: 6px;
    color: var(--text-secondary);
    text-decoration: none;
    font-size: 13px;
    transition: background 0.15s;
  }

  .service-link:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }

  .service-link .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
  }

  .dot.online { background: var(--success); }
  .dot.offline { background: var(--text-muted); }

  /* ── Main Chat Area ── */
  .main {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .chat-header {
    height: var(--header-height);
    padding: 0 24px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
    background: var(--bg-secondary);
  }

  .chat-header h1 {
    font-size: 18px;
    font-weight: 600;
  }

  .chat-header .status {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: var(--text-secondary);
  }

  .chat-header .status .spinner {
    display: none;
    width: 14px;
    height: 14px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  .chat-header .status.thinking .spinner {
    display: inline-block;
  }

  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Messages ── */
  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .messages:empty::after {
    content: 'Send a message to start chatting with the AI.\\a\\aAll tools, context, and memory are available.';
    white-space: pre-wrap;
    color: var(--text-muted);
    text-align: center;
    margin-top: 60px;
    font-size: 14px;
    line-height: 1.6;
  }

  .message {
    max-width: 85%;
    padding: 12px 16px;
    border-radius: 8px;
    line-height: 1.5;
    font-size: 14px;
    animation: fadeIn 0.2s ease;
    word-wrap: break-word;
    overflow-wrap: break-word;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .message.user {
    background: var(--user-msg);
    border: 1px solid var(--border);
    align-self: flex-end;
  }

  .message.assistant {
    background: var(--assistant-msg);
    border: 1px solid var(--border);
    align-self: flex-start;
  }

  .message .timestamp {
    font-size: 11px;
    color: var(--text-muted);
    margin-top: 6px;
  }

  .message code {
    background: var(--code-bg);
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
    font-size: 13px;
  }

  .message pre {
    background: var(--code-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px;
    margin: 8px 0;
    overflow-x: auto;
    font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
    font-size: 13px;
    line-height: 1.4;
  }

  .typing-indicator {
    display: none;
    align-self: flex-start;
    background: var(--assistant-msg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 16px;
    gap: 4px;
  }

  .typing-indicator.active {
    display: flex;
  }

  .typing-indicator span {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--text-muted);
    animation: bounce 1.4s infinite ease-in-out;
  }

  .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
  .typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

  @keyframes bounce {
    0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
    40% { transform: scale(1.2); opacity: 1; }
  }

  /* ── Input ── */
  .input-area {
    padding: 16px 24px;
    border-top: 1px solid var(--border);
    background: var(--bg-secondary);
  }

  .input-row {
    display: flex;
    gap: 8px;
    align-items: flex-end;
  }

  .input-row textarea {
    flex: 1;
    background: var(--bg-tertiary);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text-primary);
    padding: 10px 14px;
    font-size: 14px;
    font-family: inherit;
    resize: none;
    min-height: 42px;
    max-height: 200px;
    outline: none;
    transition: border-color 0.15s;
  }

  .input-row textarea:focus {
    border-color: var(--accent);
  }

  .input-row textarea::placeholder {
    color: var(--text-muted);
  }

  .input-row button {
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s;
    white-space: nowrap;
    height: 42px;
  }

  .input-row button:hover {
    background: var(--accent-hover);
  }

  .input-row button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .input-row button .icon {
    display: inline-block;
    margin-right: 4px;
  }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 8px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

  /* ── Responsive ── */
  @media (max-width: 768px) {
    .sidebar { display: none; }
    .message { max-width: 100%; }
  }
</style>
</head>
<body>

<!-- Sidebar -->
<div class="sidebar">
  <div class="sidebar-header">
    <h2>🧠 Pi Chat</h2>
    <p>RPC-powered AI assistant</p>
  </div>
  <div class="memory-panel" id="memoryPanel">
    <div class="memory-stat">
      <div class="label">Status</div>
      <div class="value" id="statusValue">Connecting...</div>
    </div>
    <div class="memory-stat">
      <div class="label">Memory</div>
      <div class="value" id="memoryValue">—</div>
    </div>
    <div class="memory-stat">
      <div class="label">Session</div>
      <div class="value" id="sessionValue">—</div>
    </div>
    <div style="margin-top: 12px; border-top: 1px solid var(--border); padding-top: 12px;">
      <a class="service-link" href="{MEMORY_WEB_URL}" target="_blank">
        <span class="dot online"></span> Memory Dashboard
      </a>
      <a class="service-link" href="{A2A_URL}" target="_blank">
        <span class="dot online"></span> A2A Connector
      </a>
      <a class="service-link" href="/" target="_blank">
        <span class="dot online"></span> Pi Chat (here)
      </a>
    </div>
    <div style="margin-top: auto; padding: 12px; font-size: 11px; color: var(--text-muted);">
      <div id="errorLog" style="display:none; color: var(--error); margin-bottom: 8px;"></div>
      <button onclick="newSession()" style="background:none; border:1px solid var(--border); color:var(--text-secondary); border-radius:6px; padding:6px 12px; cursor:pointer; font-size:12px; width:100%;">New Session</button>
    </div>
  </div>
</div>

<!-- Main Chat -->
<div class="main">
  <div class="chat-header">
    <h1>💬 Chat</h1>
    <div class="status" id="statusIndicator">
      <span class="spinner"></span>
      <span id="statusText">Ready</span>
    </div>
  </div>

  <div class="messages" id="messages"></div>

  <div class="typing-indicator" id="typingIndicator">
    <span></span><span></span><span></span>
  </div>

  <div class="input-area">
    <div class="input-row">
      <textarea id="input" rows="1" placeholder="Ask anything..." 
                onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMessage()}"></textarea>
      <button id="sendBtn" onclick="sendMessage()">
        <span class="icon">→</span> Send
      </button>
    </div>
  </div>
</div>

<script>
// ── State ──
let sessionId = localStorage.getItem('pi_chat_session') || crypto.randomUUID().slice(0, 8);
localStorage.setItem('pi_chat_session', sessionId);
let isStreaming = false;
let currentAssistantMsg = null;
let streamBuffer = '';

// ── Elements ──
const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('sendBtn');
const typingIndicator = document.getElementById('typingIndicator');
const statusIndicator = document.getElementById('statusIndicator');
const statusText = document.getElementById('statusText');
const statusValue = document.getElementById('statusValue');
const memoryValue = document.getElementById('memoryValue');
const sessionValue = document.getElementById('sessionValue');
const errorLog = document.getElementById('errorLog');

// ── Auto-resize textarea ──
inputEl.addEventListener('input', () => {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 200) + 'px';
});

// ── Utility ──
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function formatMessage(text) {
  // Handle code blocks
  let formatted = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  
  // Triple backtick code blocks
  formatted = formatted.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    return '<pre>' + escapeHtml(code) + '</pre>';
  });
  
  // Single backtick inline code
  formatted = formatted.replace(/`([^`]+)`/g, '<code>' + escapeHtml('$1') + '</code>');
  
  // Bold
  formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  
  // Italic
  formatted = formatted.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  
  // Line breaks
  formatted = formatted.replace(/\n/g, '<br>');
  
  return formatted;
}

function addMessage(role, content) {
  const div = document.createElement('div');
  div.className = 'message ' + role;
  div.innerHTML = formatMessage(content) + 
    '<div class="timestamp">' + new Date().toLocaleTimeString() + '</div>';
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

function setThinking(active) {
  if (active) {
    statusIndicator.classList.add('thinking');
    statusText.textContent = 'Thinking...';
    typingIndicator.classList.add('active');
  } else {
    statusIndicator.classList.remove('thinking');
    statusText.textContent = 'Ready';
    typingIndicator.classList.remove('active');
  }
}

function setStatus(text, isError) {
  statusValue.textContent = text;
  if (isError) statusValue.style.color = 'var(--error)';
  else statusValue.style.color = 'var(--accent)';
}

// ── Memory Status ──
async function refreshMemoryStatus() {
  try {
    const r = await fetch('/memory-status');
    const data = await r.json();
    memoryValue.textContent = data.memorySize || '—';
    sessionValue.textContent = data.sessionId || '—';
    if (data.piStatus === 'running') {
      setStatus('Pi RPC Connected');
    } else {
      setStatus('Pi RPC Disconnected', true);
    }
  } catch (e) {
    setStatus('Server Unreachable', true);
  }
}

// Refresh every 10s
refreshMemoryStatus();
setInterval(refreshMemoryStatus, 10000);

// ── Send Message ──
async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || isStreaming) return;

  inputEl.value = '';
  inputEl.style.height = 'auto';
  addMessage('user', text);
  setThinking(true);
  isStreaming = true;
  sendBtn.disabled = true;

  streamBuffer = '';
  
  // Create assistant message container
  currentAssistantMsg = document.createElement('div');
  currentAssistantMsg.className = 'message assistant';
  messagesEl.appendChild(currentAssistantMsg);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  try {
    const r = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, sessionId }),
    });

    if (!r.ok) {
      const err = await r.json().catch(() => ({ error: 'Unknown error' }));
      currentAssistantMsg.innerHTML = '<span style="color:var(--error)">Error: ' + escapeHtml(err.error) + '</span>';
      setThinking(false);
      isStreaming = false;
      sendBtn.disabled = false;
      return;
    }

    const reader = r.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6).trim();
        if (!data) continue;

        try {
          const ev = JSON.parse(data);
          
          if (ev.type === 'delta') {
            streamBuffer += ev.text;
            currentAssistantMsg.innerHTML = formatMessage(streamBuffer);
            messagesEl.scrollTop = messagesEl.scrollHeight;
          } else if (ev.type === 'done') {
            currentAssistantMsg.innerHTML = formatMessage(streamBuffer) +
              '<div class="timestamp">' + new Date().toLocaleTimeString() + '</div>';
          } else if (ev.type === 'error') {
            currentAssistantMsg.innerHTML = '<span style="color:var(--error)">Error: ' + escapeHtml(ev.text || ev.message) + '</span>';
          } else if (ev.type === 'status') {
            statusText.textContent = ev.text;
          }
        } catch (e) {
          console.error('Parse error:', e, 'line:', line);
        }
      }
    }
  } catch (e) {
    currentAssistantMsg.innerHTML = '<span style="color:var(--error)">Connection error: ' + escapeHtml(e.message) + '</span>';
  }

  setThinking(false);
  isStreaming = false;
  sendBtn.disabled = false;
  inputEl.focus();
}

// ── New Session ──
function newSession() {
  sessionId = crypto.randomUUID().slice(0, 8);
  localStorage.setItem('pi_chat_session', sessionId);
  messagesEl.innerHTML = '';
  streamBuffer = '';
  currentAssistantMsg = null;
  refreshMemoryStatus();
}

// ── Focus input on load ──
inputEl.focus();
</script>
</body>
</html>
"""


# ── HTTP Handler ─────────────────────────────────────

class ChatHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "" or path == "/":
            html = HTML_TEMPLATE.replace('{MEMORY_WEB_URL}', MEMORY_WEB_URL).replace('{A2A_URL}', A2A_URL)
            self.send_html(html)

        elif path == "/memory-status":
            self._memory_status()

        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/chat":
            self._handle_chat()
        else:
            self.send_error(404)

    def _memory_status(self):
        """Return memory system status."""
        memory_file = Path("/root/pi/COMPACTED_MEMORY.md")
        mem_size = f"{memory_file.stat().st_size} bytes" if memory_file.exists() else "No file"

        self.send_json({
            "piStatus": "running" if pi_rpc.running else "idle",
            "memorySize": mem_size,
            "sessionId": "pi-chat-rpc",
            "sessionsActive": len(sessions),
            "a2aUrl": A2A_URL,
            "memoryWebUrl": MEMORY_WEB_URL,
        })

    def _handle_chat(self):
        """Handle a chat message via SSE streaming."""
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        message = body.get("message", "").strip()
        if not message:
            self.send_json({"error": "message required"}, 400)
            return

        session_id = body.get("sessionId", "default")

        # Start SSE response
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Ensure pi RPC is running
        if not pi_rpc.running:
            if not pi_rpc.start():
                self.wfile.write(f"data: {json.dumps({'type': 'error', 'text': 'Failed to start Pi RPC process'})}\n\n".encode())
                self.wfile.flush()
                return

        # Register a queue for response events
        qid = f"chat_{session_id}_{uuid.uuid4().hex[:6]}"
        pi_rpc.register_queue(qid)
        
        try:
            # Send status event
            self.wfile.write(f"data: {json.dumps({'type': 'status', 'text': 'Sending to AI...'})}\n\n".encode())
            self.wfile.flush()

            # Send the prompt
            pi_rpc.send_command({
                "type": "prompt",
                "message": message,
            })

            buffer = ""
            done = False
            timeout = 120  # 2 minute timeout
            start = time.time()

            while not done and (time.time() - start) < timeout:
                try:
                    event = pi_rpc.get_queue(qid).get(timeout=0.5)
                except Empty:
                    # Send keepalive
                    self.wfile.write(": keepalive\n\n".encode())
                    self.wfile.flush()
                    continue

                ev_type = event.get("type")

                if ev_type == "message_update":
                    delta = event.get("assistantMessageEvent", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("delta", "")
                        if text:
                            buffer += text
                            self.wfile.write(f"data: {json.dumps({'type': 'delta', 'text': text})}\n\n".encode())
                            self.wfile.flush()
                    elif delta.get("type") == "thinking_delta":
                        # Optionally show thinking
                        pass

                elif ev_type == "turn_end":
                    # Download the full message
                    msg = event.get("message", {})
                    role = msg.get("role", "assistant")
                    content = ""
                    for block in msg.get("content", []):
                        if block.get("type") == "text":
                            content += block.get("text", "")

                elif ev_type == "agent_end":
                    # Final complete message
                    messages = event.get("messages", [])
                    for m in messages:
                        if m.get("role") == "assistant":
                            content = ""
                            for block in m.get("content", []):
                                if block.get("type") == "text":
                                    content += block.get("text", "")
                            if content:
                                # Only send if we haven't already streamed it fully
                                pass
                    done = True

                elif ev_type == "response":
                    if event.get("command") == "prompt":
                        if event.get("success"):
                            pass  # Prompt accepted
                        else:
                            self.wfile.write(f"data: {json.dumps({'type': 'error', 'text': event.get('error', 'Prompt rejected')})}\n\n".encode())
                            self.wfile.flush()
                            done = True

                elif ev_type == "agent_start":
                    self.wfile.write(f"data: {json.dumps({'type': 'status', 'text': 'AI is thinking...'})}\n\n".encode())
                    self.wfile.flush()

                elif ev_type == "compaction_end":
                    self.wfile.write(f"data: {json.dumps({'type': 'status', 'text': 'Compacting context...'})}\n\n".encode())
                    self.wfile.flush()

            # Send done event
            self.wfile.write(f"data: {json.dumps({'type': 'done'})}\n\n".encode())
            self.wfile.flush()

        except Exception as e:
            try:
                self.wfile.write(f"data: {json.dumps({'type': 'error', 'text': str(e)[:500]})}\n\n".encode())
                self.wfile.flush()
            except Exception:
                pass
        finally:
            pi_rpc.unregister_queue(qid)

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def send_html(self, content):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode())

    def send_error(self, code, message=None):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write((message or f"Error {code}").encode())

    def log_message(self, fmt, *args):
        print(f"  [Chat] {args[0]} {args[1]} {args[2]}")


def main():
    global PORT
    daemon = False
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--port" and i + 1 < len(args):
            PORT = int(args[i + 1])
        elif a == "--daemon":
            daemon = True

    # Start pi RPC
    print("  Starting Pi RPC subprocess...")
    if not pi_rpc.start():
        print("  ⚠ Failed to start Pi RPC. Chat will be unavailable.")
        print("  Make sure `pi` is installed and configured.")

    if daemon:
        pid = os.fork()
        if pid > 0:
            print(f"  Pi Chat Server — PID {pid}")
            sys.exit(0)

    server = HTTPServer(("0.0.0.0", PORT), ChatHandler)

    print(f"\n  💬 Pi Chat Server")
    print(f"  ─────────────────────")
    print(f"  Web UI:  http://localhost:{PORT}")
    print(f"  ─────────────────────")
    print(f"  Chat with the AI from your browser.")
    print(f"  Full context, tools, and memory available.")
    print(f"  Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopping...")
        pi_rpc.stop()
        server.shutdown()


if __name__ == "__main__":
    main()
