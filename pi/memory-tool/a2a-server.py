#!/usr/bin/env python3
"""
a2a-server — A2A Protocol HTTP Server + OpenClaw-style Chat Web UI
=====================================================================
"""

import json
import os
import sys
import time
import uuid
import urllib.parse
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from queue import Queue, Empty
from typing import Any, Optional

# Ensure the memory-tool directory is in the path
_p = os.path.dirname(os.path.abspath(__file__))
if _p not in sys.path:
    sys.path.insert(0, _p)

from a2a_core import AgentEvent, AgentRole, EventType, Task, TaskStatus
from a2a_agent import AgentRuntime
from a2a_memory import MemorySystem

PORT = int(os.environ.get("A2A_SERVER_PORT", 8087))
MEMORY_WEB_URL = os.environ.get("MEMORY_WEB_URL", "http://localhost:8083")
A2A_CONNECTOR_URL = os.environ.get("A2A_CONNECTOR_URL", "http://localhost:8084")

# ── Global Agent Runtime ───────────────────────────

agent = AgentRuntime(name="pi-agent", role="superior")
memory = agent.memory

sse_queues: dict[str, Queue] = {}


def sse_listener(event: AgentEvent):
    task_id = event.task_id
    if task_id in sse_queues:
        sse_queues[task_id].put(event)
    if "*" in sse_queues:
        sse_queues["*"].put(event)


agent.on_event(sse_listener)
memory.on_event(sse_listener)


# ── OpenClaw-style Web UI ──────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pi A2A Agent</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<style>
  :root {
    --bg: #0d1117;
    --bg-surface: #161b22;
    --bg-elevated: #1c2333;
    --bg-hover: #1c2128;
    --text: #e6edf3;
    --text-secondary: #8b949e;
    --text-muted: #484f58;
    --accent: #58a6ff;
    --accent-glow: rgba(88,166,255,0.15);
    --border: #30363d;
    --border-light: #21262d;
    --success: #3fb950;
    --warning: #d29922;
    --error: #f85149;
    --purple: #bc8cff;
    --orange: #f0883e;
    --radius: 10px;
    --radius-sm: 6px;
    --sidebar: 280px;
    --header: 52px;
    --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'SF Pro Text', system-ui, sans-serif;
    --mono: 'SF Mono', 'Fira Code', 'Cascadia Code', 'JetBrains Mono', monospace;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; }
  body { font-family: var(--font); background: var(--bg); color: var(--text); display: flex; overflow: hidden; -webkit-font-smoothing: antialiased; }

  /* ── Sidebar ── */
  .sidebar { width: var(--sidebar); background: var(--bg-surface); border-right: 1px solid var(--border); display: flex; flex-direction: column; flex-shrink: 0; overflow: hidden; }
  .sidebar-brand { padding: 16px 20px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 10px; }
  .sidebar-brand .logo { width: 28px; height: 28px; background: var(--accent); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 16px; color: #fff; font-weight: 700; }
  .sidebar-brand h2 { font-size: 15px; font-weight: 600; color: var(--text); }
  .sidebar-brand .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--success); margin-left: auto; }

  .sidebar-nav { padding: 8px; display: flex; flex-direction: column; gap: 2px; }
  .sidebar-nav a { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: var(--radius-sm); color: var(--text-secondary); text-decoration: none; font-size: 13px; transition: all 0.12s; }
  .sidebar-nav a:hover { background: var(--bg-hover); color: var(--text); }
  .sidebar-nav a.active { background: var(--accent-glow); color: var(--accent); }

  .sidebar-section { padding: 12px 16px; }
  .sidebar-section h3 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.8px; color: var(--text-muted); margin-bottom: 8px; font-weight: 600; }
  .stat-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; }
  .stat-row .label { color: var(--text-secondary); }
  .stat-row .value { color: var(--text); font-weight: 500; font-family: var(--mono); font-size: 12px; }

  .sidebar-services { padding: 8px 16px; border-top: 1px solid var(--border); margin-top: auto; }
  .sidebar-services a { display: flex; align-items: center; gap: 8px; padding: 6px 0; color: var(--text-muted); text-decoration: none; font-size: 12px; transition: color 0.12s; }
  .sidebar-services a:hover { color: var(--text-secondary); }
  .sidebar-services .s-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--success); }

  /* ── Main ── */
  .main { flex: 1; display: flex; flex-direction: column; min-width: 0; background: var(--bg); }
  .chat-header { height: var(--header); padding: 0 24px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; background: var(--bg); }
  .chat-header h1 { font-size: 16px; font-weight: 600; }
  .chat-header .status { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); }
  .chat-header .status .spinner { display: none; width: 12px; height: 12px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.7s linear infinite; }
  .chat-header .status.thinking .spinner { display: inline-block; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Messages ── */
  .messages { flex: 1; overflow-y: auto; padding: 20px 0; }
  .messages-inner { max-width: 820px; margin: 0 auto; display: flex; flex-direction: column; gap: 6px; padding: 0 24px; }
  .messages:empty .messages-inner::after { content: ''; } /* hide empty state if JS handles it */

  .empty-state { text-align: center; padding: 80px 24px 40px; color: var(--text-muted); max-width: 820px; margin: 0 auto; }
  .empty-state h2 { font-size: 20px; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px; }
  .empty-state p { font-size: 14px; line-height: 1.6; }
  .empty-state .examples { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-top: 20px; }
  .empty-state .examples button { background: var(--bg-surface); border: 1px solid var(--border); border-radius: 20px; padding: 8px 16px; color: var(--text-secondary); font-size: 13px; cursor: pointer; transition: all 0.12s; font-family: inherit; }
  .empty-state .examples button:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-glow); }

  /* Message bubbles */
  .msg-group { display: flex; flex-direction: column; gap: 2px; }
  .msg { display: flex; gap: 12px; padding: 8px 0; animation: msgIn 0.2s ease; }
  @keyframes msgIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
  .msg.user { flex-direction: row-reverse; }
  .msg .avatar { width: 30px; height: 30px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 15px; flex-shrink: 0; }
  .msg.user .avatar { background: var(--accent-glow); color: var(--accent); }
  .msg.assistant .avatar { background: rgba(188,140,255,0.12); color: var(--purple); }
  .msg .bubble { max-width: 85%; padding: 10px 16px; border-radius: var(--radius); line-height: 1.6; font-size: 14px; word-wrap: break-word; overflow-wrap: break-word; }
  .msg.user .bubble { background: var(--accent); color: #fff; border-bottom-right-radius: 4px; }
  .msg.assistant .bubble { background: var(--bg-surface); border: 1px solid var(--border); color: var(--text); border-bottom-left-radius: 4px; }

  /* Markdown inside bubbles */
  .bubble p { margin: 4px 0; }
  .bubble p:first-child { margin-top: 0; }
  .bubble p:last-child { margin-bottom: 0; }
  .bubble code { background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px; font-family: var(--mono); font-size: 13px; }
  .bubble pre { background: var(--bg); border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 12px; margin: 8px 0; overflow-x: auto; font-family: var(--mono); font-size: 13px; line-height: 1.4; }
  .bubble pre code { background: none; padding: 0; border-radius: 0; }
  .bubble strong { font-weight: 600; }
  .bubble em { font-style: italic; }
  .bubble ul, .bubble ol { margin: 4px 0; padding-left: 20px; }
  .bubble li { margin: 2px 0; }
  .bubble a { color: var(--accent); text-decoration: none; }
  .bubble a:hover { text-decoration: underline; }
  .bubble h1, .bubble h2, .bubble h3, .bubble h4 { margin: 12px 0 6px; font-weight: 600; line-height: 1.3; }
  .bubble h2 { font-size: 16px; color: var(--accent); }
  .bubble h3 { font-size: 14px; color: var(--text-secondary); }

  .msg.user .bubble code { background: rgba(255,255,255,0.15); }
  .msg.user .bubble pre { background: rgba(0,0,0,0.2); border-color: rgba(255,255,255,0.1); }

  /* Thinking block */
  .thinking-block { margin: 4px 0; }
  .thinking-toggle { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted); cursor: pointer; padding: 2px 8px; border-radius: 4px; transition: all 0.12s; user-select: none; }
  .thinking-toggle:hover { color: var(--text-secondary); background: var(--bg-hover); }
  .thinking-toggle .arrow { transition: transform 0.15s; font-size: 10px; }
  .thinking-toggle.open .arrow { transform: rotate(90deg); }
  .thinking-content { display: none; padding: 8px 12px; margin: 4px 0; background: rgba(88,166,255,0.04); border-left: 2px solid var(--accent); border-radius: 0 var(--radius-sm) var(--radius-sm) 0; font-size: 13px; color: var(--text-secondary); line-height: 1.5; white-space: pre-wrap; font-style: italic; max-height: 300px; overflow-y: auto; }
  .thinking-content.open { display: block; }

  /* Tool call card */
  .tool-card { margin: 6px 0; border: 1px solid var(--border-light); border-radius: var(--radius-sm); overflow: hidden; background: var(--bg); }
  .tool-card-header { display: flex; align-items: center; gap: 8px; padding: 8px 12px; cursor: pointer; user-select: none; transition: background 0.12s; }
  .tool-card-header:hover { background: var(--bg-hover); }
  .tool-card-header .tool-icon { font-size: 14px; }
  .tool-card-header .tool-name { font-size: 13px; font-weight: 500; color: var(--text); font-family: var(--mono); }
  .tool-card-header .tool-status { font-size: 11px; margin-left: auto; color: var(--text-muted); }
  .tool-card-header .tool-arrow { transition: transform 0.15s; font-size: 10px; color: var(--text-muted); }
  .tool-card-header.open .tool-arrow { transform: rotate(90deg); }
  .tool-card-body { display: none; border-top: 1px solid var(--border-light); }
  .tool-card-body.open { display: block; }
  .tool-card-body pre { margin: 0; padding: 10px 12px; font-family: var(--mono); font-size: 12px; line-height: 1.4; white-space: pre-wrap; word-break: break-all; max-height: 300px; overflow: auto; color: var(--text-secondary); background: transparent; border: none; }
  .tool-card-body .tool-result-success { border-left: 3px solid var(--success); }
  .tool-card-body .tool-result-error { border-left: 3px solid var(--error); }

  /* Memory badge */
  .memory-badge { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 10px; font-size: 11px; background: rgba(63,185,80,0.08); color: var(--success); margin: 2px 0; }

  /* ── Input ── */
  .input-area { padding: 12px 24px 20px; border-top: 1px solid var(--border); background: var(--bg); }
  .input-inner { max-width: 820px; margin: 0 auto; }
  .input-row { display: flex; gap: 8px; align-items: flex-end; background: var(--bg-surface); border: 1px solid var(--border); border-radius: 12px; padding: 6px 6px 6px 16px; transition: border-color 0.15s; }
  .input-row:focus-within { border-color: var(--accent); }
  .input-row textarea { flex: 1; background: none; border: none; color: var(--text); font-size: 14px; font-family: inherit; resize: none; min-height: 24px; max-height: 160px; outline: none; padding: 8px 0; line-height: 1.5; }
  .input-row textarea::placeholder { color: var(--text-muted); }
  .input-row button { background: var(--accent); color: #fff; border: none; border-radius: 8px; width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.12s; flex-shrink: 0; font-size: 18px; }
  .input-row button:hover { background: var(--accent-hover); transform: scale(1.05); }
  .input-row button:disabled { opacity: 0.3; cursor: not-allowed; transform: none; }

  .input-tools { display: flex; gap: 4px; padding: 4px 0 0 4px; }
  .input-tools .tool-tip { font-size: 11px; color: var(--text-muted); padding: 2px 8px; border-radius: 4px; background: var(--bg-hover); }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

  @media (max-width: 768px) { .sidebar { display: none; } }
</style>
</head>
<body>

<!-- Sidebar -->
<div class="sidebar">
  <div class="sidebar-brand">
    <div class="logo">π</div>
    <h2>Pi Agent</h2>
    <span class="dot"></span>
  </div>
  <div class="sidebar-nav">
    <a href="#" class="active" onclick="return false">💬 Chat</a>
    <a href="__MEMORY_WEB_URL__" target="_blank">📖 Memory</a>
    <a href="__A2A_CONNECTOR_URL__" target="_blank">🔗 A2A</a>
  </div>
  <div class="sidebar-section">
    <h3>Agent</h3>
    <div class="stat-row"><span class="label">Status</span><span class="value" id="sStatus">Ready</span></div>
    <div class="stat-row"><span class="label">Memory</span><span class="value" id="sMemory">0</span></div>
    <div class="stat-row"><span class="label">Tasks</span><span class="value" id="sTasks">0</span></div>
    <div class="stat-row"><span class="label">Tools</span><span class="value" id="sTools">10</span></div>
  </div>
  <div class="sidebar-section" id="toolList" style="flex:1; overflow-y:auto;">
    <h3>Tools</h3>
  </div>
  <div class="sidebar-services">
    <a href="__MEMORY_WEB_URL__" target="_blank"><span class="s-dot"></span> Memory Dashboard</a>
    <a href="__A2A_CONNECTOR_URL__" target="_blank"><span class="s-dot"></span> A2A Connector</a>
  </div>
</div>

<!-- Main -->
<div class="main">
  <div class="chat-header">
    <h1>💬 Chat</h1>
    <div class="status" id="statusBar">
      <span class="spinner"></span>
      <span id="statusText">Ready</span>
    </div>
  </div>

  <!-- Messages -->
  <div class="messages" id="messages">
    <div class="empty-state" id="emptyState">
      <h2>How can I help?</h2>
      <p>I have tools for code execution, file operations, browser automation, memory, and delegation.</p>
      <div class="examples">
        <button onclick="quickQuery('Run `ls -la /root/pi/memory-tool/`')">📂 List files</button>
        <button onclick="quickQuery('Check browser status')">🌐 Browser status</button>
        <button onclick="quickQuery('Search memory for A2A')">🔍 Search memory</button>
        <button onclick="quickQuery('Show me the skill library')">📚 Skills</button>
      </div>
    </div>
    <div class="messages-inner" id="messagesInner"></div>
  </div>

  <!-- Input -->
  <div class="input-area">
    <div class="input-inner">
      <div class="input-row">
        <textarea id="input" rows="1" placeholder="Ask the agent..." 
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMessage()}"></textarea>
        <button id="sendBtn" onclick="sendMessage()">→</button>
      </div>
      <div class="input-tools">
        <span class="tool-tip">Enter to send · Shift+Enter for newline</span>
      </div>
    </div>
  </div>
</div>

<script>
// ── State ──
let isProcessing = false;
let currentAssistantBubble = null;
let currentThoughtBuffer = '';
let currentTextBuffer = '';
let currentToolCall = null;
let toolCallResults = {};
let streamActive = false;

// ── Elements ──
const messages = document.getElementById('messages');
const messagesInner = document.getElementById('messagesInner');
const emptyState = document.getElementById('emptyState');
const input = document.getElementById('input');
const sendBtn = document.getElementById('sendBtn');
const statusBar = document.getElementById('statusBar');
const statusText = document.getElementById('statusText');

// ── Auto-resize ──
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 160) + 'px';
});

// ── Escape HTML ──
function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ── Render markdown (simple) ──
function renderMarkdown(text) {
  if (!text) return '';
  let html = esc(text);
  // Code blocks
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    return '<pre><code>' + esc(code) + '</code></pre>';
  });
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>' + esc('$1') + '</code>');
  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Italic
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
  // Lists
  html = html.replace(/^\s*[-*]\s+(.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
  // Headers
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  // Paragraphs
  html = html.replace(/\n\n/g, '</p><p>');
  html = '<p>' + html + '</p>';
  // Clean empty ps
  html = html.replace(/<p><\/p>/g, '');
  return html;
}

// ── Add user message ──
function addUserMessage(text) {
  emptyState.style.display = 'none';
  const div = document.createElement('div');
  div.className = 'msg user';
  div.innerHTML = '<div class="avatar">👤</div><div class="bubble">' + esc(text).replace(/\n/g, '<br>') + '</div>';
  messagesInner.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

// ── Create assistant message container ──
function createAssistantMessage() {
  emptyState.style.display = 'none';
  currentThoughtBuffer = '';
  currentTextBuffer = '';

  const group = document.createElement('div');
  group.className = 'msg-group';
  group.id = 'currentAssistant';

  const msg = document.createElement('div');
  msg.className = 'msg assistant';
  msg.innerHTML = '<div class="avatar">🤖</div><div class="bubble" id="assistantBubble"></div>';
  group.appendChild(msg);
  messagesInner.appendChild(group);
  messages.scrollTop = messages.scrollHeight;

  currentAssistantBubble = document.getElementById('assistantBubble');
  return currentAssistantBubble;
}

// ── Add thinking section to current assistant message ──
function ensureThinkingBlock() {
  if (!currentAssistantBubble) return null;
  let tb = currentAssistantBubble.querySelector('.thinking-block');
  if (!tb) {
    tb = document.createElement('div');
    tb.className = 'thinking-block';
    tb.innerHTML = '<div class="thinking-toggle" onclick="this.classList.toggle(\'open\');this.nextElementSibling.classList.toggle(\'open\')"><span class="arrow">▶</span> Show thinking</div><div class="thinking-content" id="thinkingContent"></div>';
    currentAssistantBubble.appendChild(tb);
  }
  return tb.querySelector('.thinking-content');
}

// ── Add tool call card ──
function addToolCall(toolName, args) {
  if (!currentAssistantBubble) createAssistantMessage();
  const container = currentAssistantBubble;

  const card = document.createElement('div');
  card.className = 'tool-card';
  card.innerHTML = '<div class="tool-card-header" onclick="this.classList.toggle(\'open\');this.nextElementSibling.classList.toggle(\'open\')">' +
    '<span class="tool-icon">🔧</span>' +
    '<span class="tool-name">' + esc(toolName) + '</span>' +
    '<span class="tool-status" id="toolStatus_' + Date.now() + '">running...</span>' +
    '<span class="tool-arrow">▶</span></div>' +
    '<div class="tool-card-body"><pre>' + esc(JSON.stringify(args, null, 2)) + '</pre></div>';
  container.appendChild(card);
  messages.scrollTop = messages.scrollHeight;
  return card;
}

// ── Update tool call result ──
function updateToolResult(toolName, output, isError) {
  const statusEl = document.querySelector('.tool-status');
  if (statusEl) {
    statusEl.textContent = isError ? 'failed' : 'done';
    statusEl.style.color = isError ? 'var(--error)' : 'var(--success)';
  }
  const lastCard = document.querySelector('.tool-card:last-child .tool-card-body');
  if (lastCard) {
    const div = document.createElement('div');
    div.className = isError ? 'tool-result-error' : 'tool-result-success';
    const pre = document.createElement('pre');
    pre.textContent = output.slice(0, 2000);
    div.appendChild(pre);
    lastCard.appendChild(div);
    lastCard.classList.add('open');
    lastCard.previousElementSibling.classList.add('open');
  }
  messages.scrollTop = messages.scrollHeight;
}

// ── Set thinking ──
function setThinking(active) {
  if (active) {
    statusBar.classList.add('thinking');
    statusText.textContent = 'Thinking...';
  } else {
    statusBar.classList.remove('thinking');
    statusText.textContent = 'Ready';
  }
}

// ── Send Message ──
async function sendMessage() {
  const text = input.value.trim();
  if (!text || isProcessing) return;

  input.value = '';
  input.style.height = 'auto';
  addUserMessage(text);
  setThinking(true);
  isProcessing = true;
  sendBtn.disabled = true;

  currentAssistantBubble = null;
  currentThoughtBuffer = '';
  currentTextBuffer = '';
  streamActive = true;

  try {
    const r = await fetch('/a2a/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });

    if (!r.ok) {
      createAssistantMessage();
      currentAssistantBubble.innerHTML = '<span style="color:var(--error)">Error: ' + r.status + '</span>';
      return;
    }

    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let thoughtContent = '';
    let textContent = '';
    let toolCallData = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (!payload) continue;

        try {
          const ev = JSON.parse(payload);
          const type = ev.type;
          const data = ev.data || {};

          if (type === 'status') {
            statusText.textContent = data.text || '...';
          }
          else if (type === 'thought_delta' || type === 'thought') {
            const delta = data.delta || data.text || '';
            if (delta) {
              thoughtContent += delta;
              const tc = ensureThinkingBlock();
              if (tc) tc.textContent = thoughtContent;
            }
          }
          else if (type === 'text_delta') {
            const delta = data.delta || '';
            if (delta) {
              textContent += delta;
              if (!currentAssistantBubble) createAssistantMessage();
              currentAssistantBubble.innerHTML = renderMarkdown(textContent);
            }
          }
          else if (type === 'text') {
            const finalText = data.text || '';
            if (finalText && !textContent) {
              textContent = finalText;
              if (!currentAssistantBubble) createAssistantMessage();
              currentAssistantBubble.innerHTML = renderMarkdown(finalText);
            }
          }
          else if (type === 'tool_call') {
            const tn = data.tool_name || '';
            const args = data.arguments || {};
            if (!currentAssistantBubble) createAssistantMessage();
            addToolCall(tn, args);
            toolCallData = { name: tn, args };
          }
          else if (type === 'tool_result') {
            const tn = data.tool_name || '';
            const output = data.output || '';
            const isErr = data.is_error || false;
            updateToolResult(tn, output, isErr);
          }
          else if (type === 'memory_store') {
            // Subtle memory badge
          }
          else if (type === 'done') {
            streamActive = false;
          }
        } catch(e) {
          console.error('Parse:', e);
        }
      }
    }
  } catch(e) {
    if (!currentAssistantBubble) createAssistantMessage();
    currentAssistantBubble.innerHTML = '<span style="color:var(--error)">Connection: ' + esc(e.message) + '</span>';
  }

  setThinking(false);
  isProcessing = false;
  sendBtn.disabled = false;
  streamActive = false;
  input.focus();
}

// ── Quick query ──
function quickQuery(text) {
  input.value = text;
  sendMessage();
}

// ── Refresh sidebar ──
async function refreshSidebar() {
  try {
    const r = await fetch('/a2a/status');
    const data = await r.json();
    document.getElementById('sMemory').textContent = data.memory?.vector_count || 0;
    document.getElementById('sTasks').textContent = data.tasks?.task_count || 0;
    document.getElementById('sTools').textContent = data.tools || '—';

    // Tool list
    const card = await fetch('/.well-known/agent.json');
    const cardData = await card.json();
    const toolList = document.getElementById('toolList');
    if (cardData.capabilities) {
      let html = '<h3>Tools</h3>';
      cardData.capabilities.forEach(c => {
        const icons = { memory_search: '🔍', memory_store: '💾', bash: '⌨️', python: '🐍', delegate: '📤', list_subordinates: '📋', read_file: '📄', cat: '🐱', browser: '🌐', skill: '📚' };
        html += '<div class="stat-row"><span class="label">' + (icons[c] || '•') + ' ' + c + '</span></div>';
      });
      toolList.innerHTML = html;
    }
  } catch(e) {}
}
refreshSidebar();
setInterval(refreshSidebar, 10000);

input.focus();
</script>
</body>
</html>
"""


# ── HTTP Server ────────────────────────────────────

class A2AServerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path in ("", "/"):
            html = HTML_TEMPLATE
            html = html.replace("__MEMORY_WEB_URL__", MEMORY_WEB_URL)
            html = html.replace("__A2A_CONNECTOR_URL__", A2A_CONNECTOR_URL)
            self.send_html(html)

        elif path == "/.well-known/agent.json":
            card = agent.get_card().to_dict()
            card["server_url"] = f"http://localhost:{PORT}"
            self.send_json(card)

        elif path == "/a2a/health":
            self.send_json({
                "status": "ok",
                "agent": agent.name,
                "tasks": len(agent.tasks.list_tasks()),
                "tools": len(agent.tools.list_tools()),
                "memory": memory.status(),
            })

        elif path == "/a2a/status":
            self.send_json(agent.status())

        elif path == "/a2a/tasks":
            tasks = agent.tasks.list_tasks()
            self.send_json({
                "tasks": [t.to_dict() for t in tasks[:50]],
                "count": len(tasks),
            })

        elif path.startswith("/a2a/tasks/") and path.endswith("/stream"):
            task_id = path.split("/")[3]
            self._handle_task_stream(task_id)

        elif path.startswith("/a2a/tasks/"):
            task_id = path.split("/")[3]
            task = agent.tasks.get_task(task_id)
            if task:
                self.send_json(task.to_dict())
            else:
                self.send_json({"error": "Task not found"}, 404)

        else:
            self.send_json({"error": "Not found", "path": path}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/a2a/chat":
            self._handle_chat()
        elif path == "/a2a/tasks":
            self._handle_create_task()
        elif path == "/a2a/memory/search":
            self._handle_memory_search()
        elif path == "/a2a/memory/store":
            self._handle_memory_store()
        else:
            self.send_json({"error": "Not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _handle_chat(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        message = body.get("message", "").strip()

        if not message:
            self.send_json({"error": "message required"}, 400)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        task_id = f"chat_{uuid.uuid4().hex[:8]}"
        q = Queue()
        sse_queues[task_id] = q

        def cleanup():
            sse_queues.pop(task_id, None)

        try:
            import threading
            def run_query():
                try:
                    agent.process_query(query=message, task_id=task_id, stream=True)
                except Exception as e:
                    q.put(AgentEvent.error(task_id, str(e)))
                    q.put(AgentEvent.done(task_id))

            t = threading.Thread(target=run_query, daemon=True)
            t.start()

            timeout = 180
            start = time.time()

            while (time.time() - start) < timeout:
                try:
                    event = q.get(timeout=1)
                    sse_data = event.to_sse()
                    try:
                        self.wfile.write(sse_data.encode())
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        break
                    if event.type == EventType.DONE:
                        break
                except Empty:
                    try:
                        self.wfile.write(": keepalive\n\n".encode())
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        break

            if (time.time() - start) >= timeout:
                try:
                    err = AgentEvent.error(task_id, "Request timed out")
                    self.wfile.write(err.to_sse().encode())
                    self.wfile.flush()
                except Exception:
                    pass

        except Exception as e:
            try:
                err = AgentEvent.error(task_id, str(e))
                self.wfile.write(err.to_sse().encode())
                self.wfile.flush()
            except Exception:
                pass
        finally:
            cleanup()

    def _handle_task_stream(self, task_id: str):
        q = Queue()
        sse_queues[task_id] = q
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            timeout = 180
            start = time.time()
            while (time.time() - start) < timeout:
                try:
                    event = q.get(timeout=1)
                    self.wfile.write(event.to_sse().encode())
                    self.wfile.flush()
                    if event.type in (EventType.DONE, EventType.ERROR):
                        break
                except Empty:
                    self.wfile.write(": keepalive\n\n".encode())
                    self.wfile.flush()
        except Exception:
            pass
        finally:
            sse_queues.pop(task_id, None)

    def _handle_create_task(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        query = body.get("query", body.get("message", ""))
        if not query:
            self.send_json({"error": "query or message required"}, 400)
            return
        task = agent.tasks.create_task(query=query)
        self.send_json(task.to_dict())
        import threading
        t = threading.Thread(
            target=agent.process_query, args=(query,),
            kwargs={"task_id": task.id}, daemon=True,
        )
        t.start()

    def _handle_memory_search(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        query = body.get("query", "")
        limit = body.get("limit", 5)
        results = memory.recall(query, limit=limit)
        self.send_json({"results": [r.to_dict() for r in results], "count": len(results)})

    def _handle_memory_store(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        text = body.get("text", "")
        source = body.get("source", "api")
        if text:
            entry = memory.store(text, source=source)
            self.send_json({"stored": True, "id": entry.id if entry else None})
        else:
            self.send_json({"error": "text required"}, 400)

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, default=str).encode())

    def send_html(self, content):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode())

    def log_message(self, fmt, *args):
        print(f"  [A2AServer] {args[0]} {args[1]} {args[2]}")


def main():
    global PORT
    daemon = False
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--port" and i + 1 < len(args):
            PORT = int(args[i + 1])
        elif a == "--daemon":
            daemon = True

    mem_status = memory.status()
    print(f"  Memory: {mem_status['vector_count']} vectors | {mem_status['embedding_model']}")

    if daemon:
        pid = os.fork()
        if pid > 0:
            print(f"  Pi A2A Agent Server — PID {pid}")
            sys.exit(0)

    # Brief pause to let parent exit if daemonized
    time.sleep(1)

    server = HTTPServer(("0.0.0.0", PORT), A2AServerHandler)

    print(f"\n  🤖 Pi A2A Agent Server")
    print(f"  ───────────────────────")
    print(f"  Web UI:      http://localhost:{PORT}")
    print(f"  Agent Card:  http://localhost:{PORT}/.well-known/agent.json")
    print(f"  Chat API:    POST http://localhost:{PORT}/a2a/chat")
    print(f"  ───────────────────────")
    print(f"  OpenClaw-style UI — message bubbles, collapsible thoughts & tool calls.")
    print(f"  Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopping...")
        server.shutdown()


if __name__ == "__main__":
    main()
