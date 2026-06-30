# Session Memory — A2A Agent Protocol Build

## What Was Built
Created a full A2A (Agent-to-Agent) protocol stack replacing the RPC wrapper approach. Six files, all real code:

### Files
| File | Purpose |
|------|---------|
| `a2a_core.py` | Protocol types, task lifecycle, event model, tool registry, thread-safe TaskManager |
| `a2a_memory.py` | Vector memory system: Qdrant + Mistral embeddings + Supabase REST logging |
| `a2a_tmux.py` | Subordinate agent manager — spawns persistent tmux sessions for workers |
| `a2a_agent.py` | Agent runtime: LLM loop (Mistral API), tool execution, memory integration, hierarchy |
| `a2a-server.py` | HTTP server: Web UI, A2A endpoints, SSE streaming for thoughts/tools/results |
| `a2a-task-worker.py` | Subordinate task worker — runs inside tmux, reads .task files, writes .result |

### Running
- **A2A Web UI**: https://excessive-reading-waiver-wires.trycloudflare.com (port 8086 local)
- **Agent Card**: `/.well-known/agent.json` (7 tools)
- **Chat API**: `POST /a2a/chat` (SSE event stream)
- **Memory**: Qdrant + Mistral embed + Supabase
- **Subordinates**: tmux-ready, zero sessions currently

### CodeRabbit Fixes
- Full UUIDs for task IDs (was truncated to 12 chars)
- Thread safety with `threading.Lock` on TaskManager
- `tool_call_id` passthrough in ToolRegistry.execute()
- `process_query()` preserves passed-in `task_id`
- Decorator support in `register()`
- Per-task exception handling in worker loop
- `list_sessions()` uses proper tmux wrapper

## Infrastructure
- Mistral API key configured for embeddings + chat
- Supabase project `bzhckcqydsqlsfgdgopm` connected (moltcorp_transaction_logs table)
- Qdrant in local mode (no server running)
- tmux available, no active sessions
- Cloudflared tunnel live

## Old Services Killed
- `pi-chat-server.py` (:8085) — replaced by A2A Server
- `a2a-server.py` (old stub, :8084) — kept for backward compat

## Next
- Seed Qdrant with actual vectors (memory entries)
- Spawn test subordinate in tmux, verify delegation
- Wire Agent Zero to discover this agent via Agent Card
