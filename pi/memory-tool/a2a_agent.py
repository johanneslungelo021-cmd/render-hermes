#!/usr/bin/env python3
"""
a2a-agent — Agent Runtime (Superior + Subordinate)
=====================================================
The core agent loop with:
  - LLM interaction (via pi RPC, Mistral API, or pluggable backend)
  - Tool execution with mid-turn callbacks (agent calls tool → host runs it → result back)
  - Memory integration (recall before turn, store after)
  - Superior/subordinate hierarchy (delegate tasks to tmux workers)
  - Event streaming (thoughts, tool calls, results, text)

Usage:
  from a2a_agent import AgentRuntime
  agent = AgentRuntime()
  result = agent.process_query("Analyze the market")
"""

import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Callable

import requests

# Ensure the memory-tool directory is in the path
_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

from a2a_core import (
    AgentCard, AgentEvent, AgentMessage, AgentRole, EventType,
    Task, TaskManager, TaskStatus, ToolCall, ToolRegistry, ToolResult,
)
from a2a_memory import MemorySystem
from a2a_tmux import TmuxManager, TmuxSubordinate

# ── Config ──────────────────────────────────────────

# ── LLM Config ──
# Supports Mistral (default) or any OpenAI-compatible provider.
# Set LLM_PROVIDER=mistral or LLM_PROVIDER=opencode
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "mistral")

# Mistral defaults (used when LLM_PROVIDER=mistral or as fallback)
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
MISTRAL_API_URL = os.environ.get(
    "MISTRAL_API_URL",
    "https://api.mistral.ai/v1",
)
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-large-latest")

# OpenCode defaults (used when LLM_PROVIDER=opencode)
OPENCODE_API_KEY = os.environ.get("OPENCODE_API_KEY", "")
OPENCODE_API_URL = os.environ.get(
    "OPENCODE_API_URL",
    "https://opencode.ai/zen/v1",
)
# Model name for OpenCode provider
OPENCODE_MODEL = os.environ.get("OPENCODE_MODEL", "deepseek-v4-flash-free")

# Resolve active LLM config based on provider
if LLM_PROVIDER == "opencode":
    LLM_API_KEY = OPENCODE_API_KEY
    LLM_API_URL = OPENCODE_API_URL
    LLM_MODEL = OPENCODE_MODEL
else:
    LLM_API_KEY = MISTRAL_API_KEY
    LLM_API_URL = MISTRAL_API_URL
    LLM_MODEL = MISTRAL_MODEL

AGENT_NAME = os.environ.get("A2A_AGENT_NAME", "pi-agent")
AGENT_VERSION = os.environ.get("A2A_AGENT_VERSION", "1.0.0")


# ── LLM Backend ────────────────────────────────────

class LLMBackend:
    """Pluggable LLM backend. Supports any OpenAI-compatible API."""

    def __init__(self, api_url: str = LLM_API_URL,
                 api_key: str = LLM_API_KEY,
                 model: str = LLM_MODEL):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def chat(self, messages: list[dict], tools: Optional[list[dict]] = None,
             stream_callback: Optional[Callable[[dict], None]] = None) -> dict:
        """
        Send a chat completion request.
        If stream_callback is provided, streams deltas in real-time.
        Returns the final assistant message.
        """
        body = {
            "model": self.model,
            "messages": messages,
            "stream": stream_callback is not None,
            "max_tokens": 8192,
        }
        if tools:
            body["tools"] = tools

        if stream_callback:
            return self._stream_chat(body, stream_callback)
        else:
            return self._simple_chat(body)

    def _simple_chat(self, body: dict) -> dict:
        resp = requests.post(
            f"{self.api_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"] if data.get("choices") else {}

    def _stream_chat(self, body: dict,
                     callback: Callable[[dict], None]) -> dict:
        """Stream chat with real-time deltas. Returns the assembled message."""
        body["stream"] = True
        resp = requests.post(
            f"{self.api_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            stream=True,
            timeout=120,
        )
        resp.raise_for_status()

        role = "assistant"
        content = ""
        tool_calls = []

        for line in resp.iter_lines():
            if not line:
                continue
            if line.startswith(b"data: "):
                chunk = line[6:]
                if chunk.strip() == b"[DONE]":
                    break
                try:
                    data = json.loads(chunk)
                except json.JSONDecodeError:
                    continue

                delta = data.get("choices", [{}])[0].get("delta", {})

                if delta.get("role"):
                    role = delta["role"]
                if delta.get("content"):
                    content += delta["content"]
                    callback({"type": "text_delta", "delta": delta["content"]})

                if delta.get("tool_calls"):
                    for tc in delta["tool_calls"]:
                        idx = tc.get("index", 0)
                        if idx >= len(tool_calls):
                            tool_calls.append({
                                "id": tc.get("id", f"call_{idx}"),
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            })
                        tc_data = tool_calls[idx]
                        if tc.get("id"):
                            tc_data["id"] = tc["id"]
                        if tc.get("function", {}).get("name"):
                            tc_data["function"]["name"] += tc["function"]["name"]
                            callback({"type": "tool_name_delta", "name": tc["function"]["name"]})
                        if tc.get("function", {}).get("arguments"):
                            tc_data["function"]["arguments"] += tc["function"]["arguments"]
                            callback({"type": "tool_args_delta", "args": tc["function"]["arguments"]})

        # Build final message
        message = {"role": role, "content": content}
        if tool_calls:
            message["tool_calls"] = tool_calls

        return message

    def embed(self, text: str) -> list[float]:
        """Generate embedding (delegates to memory system's embedder)."""
        resp = requests.post(
            f"{self.api_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": "mistral-embed", "input": text},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


# ── System Prompt ──────────────────────────────────

SYSTEM_PROMPT = """You are an AI agent in a multi-agent system. You have access to tools that let you perform actions on the host machine and delegate work to subordinate agents.

## Core Rules
1. You can use tools to execute code, search memory, and browse the web.
2. When you need a tool, use the `tool_calls` format. The system will execute the tool and give you the result.
3. You can delegate tasks to subordinate agents for long-running or parallel work.
4. Your memory system stores important information between sessions — use `memory_store` to save learnings and `memory_search` to recall them.
5. Think step by step. Show your reasoning.

## Available Tools
{tools_description}

## Memory Context
{memory_context}

## Hierarchy
- You are a {role} agent.
- Your name is {agent_name}.
- Your parent is {parent}.
- You have {children} subordinate agent(s) available for delegation.
"""


# ── Agent Runtime ──────────────────────────────────

class AgentRuntime:
    """The main agent runtime with tool execution loop and hierarchy."""

    def __init__(self, name: str = AGENT_NAME, role: str = "superior",
                 llm: Optional[LLMBackend] = None,
                 memory: Optional[MemorySystem] = None,
                 task_manager: Optional[TaskManager] = None,
                 tmux_manager: Optional[TmuxManager] = None):
        self.name = name
        self.role = role
        self.llm = llm or LLMBackend()
        self.memory = memory or MemorySystem()
        self.tasks = task_manager or TaskManager()
        self.tmux = tmux_manager or TmuxManager()
        self.tools = ToolRegistry()
        self._event_listeners: list[Callable[[AgentEvent], None]] = []
        self._setup_default_tools()

        # Wire up memory events
        self.memory.on_event(lambda e: self._emit(e))
        self.tasks.on_event(lambda e: self._emit(e))

    def _setup_default_tools(self):
        """Register the default tool set."""

        @self.tools.register("memory_search", description="Search past conversations and learnings",
                             schema={
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string", "description": "What to search for"},
                                    "limit": {"type": "integer", "default": 5},
                                },
                                "required": ["query"],
                             })
        def memory_search(args: dict) -> str:
            results = self.memory.recall(args.get("query", ""), limit=args.get("limit", 5))
            if not results:
                return "No relevant memories found."
            return "\n".join(f"- [{m.source}] {m.text[:500]}" for m in results)

        @self.tools.register("memory_store", description="Store a learning or fact in persistent memory",
                             schema={
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string", "description": "What to remember"},
                                    "source": {"type": "string", "default": "agent_learning"},
                                },
                                "required": ["text"],
                             })
        def memory_store(args: dict) -> str:
            self.memory.store(
                args.get("text", ""),
                source=args.get("source", "agent_learning"),
                agent_name=self.name,
                task_id=self.tasks.list_tasks()[0].id if self.tasks.list_tasks() else "",
            )
            return "Stored in memory."

        @self.tools.register("bash", description="Run bash command on the host",
                             schema={
                                "type": "object",
                                "properties": {
                                    "command": {"type": "string", "description": "Command to run"},
                                },
                                "required": ["command"],
                             })
        def bash(args: dict) -> str:
            cmd = args.get("command", "")
            result = subprocess.run(
                ["bash", "-c", cmd],
                capture_output=True, text=True, timeout=30,
            )
            output = result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout
            if result.stderr:
                output += f"\nSTDERR: {result.stderr[-500:]}"
            return output

        @self.tools.register("python", description="Run Python code on the host",
                             schema={
                                "type": "object",
                                "properties": {
                                    "code": {"type": "string", "description": "Python code to execute"},
                                },
                                "required": ["code"],
                             })
        def python(args: dict) -> str:
            code = args.get("code", "")
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True, text=True, timeout=30,
            )
            output = result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout
            if result.stderr:
                output += f"\nSTDERR: {result.stderr[-500:]}"
            return output

        @self.tools.register("delegate", description="Delegate a task to a subordinate agent",
                             schema={
                                "type": "object",
                                "properties": {
                                    "subordinate": {"type": "string", "description": "Name of subordinate agent"},
                                    "task": {"type": "string", "description": "Task description"},
                                },
                                "required": ["subordinate", "task"],
                             })
        def delegate(args: dict) -> str:
            sub_name = args.get("subordinate", "")
            task_desc = args.get("task", "")
            sub = self.tmux.get(sub_name)
            if not sub:
                sub = self.tmux.create(sub_name)
                sub.spawn()
            task_id = sub.send_task({"query": task_desc})
            result = sub.wait_for_result(task_id, timeout=300)
            return json.dumps(result, indent=2)

        @self.tools.register("list_subordinates", description="List available subordinate agents",
                             schema={
                                "type": "object",
                                "properties": {},
                             })
        def list_subordinates(args: dict) -> str:
            sessions = self.tmux.list_sessions()
            if not sessions:
                return "No subordinate agents running."
            return "Available:\n" + "\n".join(
                f"  - {s['name']} ({s['windows']} windows)"
                for s in sessions
            )

        @self.tools.register("read_file", description="Read a file from the host filesystem",
                             schema={
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string", "description": "Path to file"},
                                },
                                "required": ["path"],
                             })
        def read_file(args: dict) -> str:
            path = args.get("path", "")
            try:
                content = Path(path).read_text()
                return content[:5000]
            except Exception as e:
                return f"Error: {e}"

        @self.tools.register("cat", description="Read one or more files (like cat)",
                             schema={
                                "type": "object",
                                "properties": {
                                    "paths": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "File paths to read",
                                    },
                                    "line_numbers": {
                                        "type": "boolean",
                                        "default": False,
                                        "description": "Show line numbers"
                                    },
                                },
                                "required": ["paths"],
                             })
        def cat(args: dict) -> str:
            paths = args.get("paths", [])
            show_numbers = args.get("line_numbers", False)
            if isinstance(paths, str):
                paths = [paths]
            parts = []
            for p in paths:
                try:
                    content = Path(p).read_text()
                    if show_numbers:
                        lines = content.split("\n")
                        content = "\n".join(f"{i+1:4d} {l}" for i, l in enumerate(lines))
                    if len(paths) > 1:
                        parts.append(f"/* {p} */")
                    parts.append(content[-10000:] if len(content) > 10000 else content)
                except Exception as e:
                    parts.append(f"{p}: Error: {e}")
            return "\n".join(parts)

        @self.tools.register("browser", description="Browser automation — navigate, capture, screenshot",
                             schema={
                                "type": "object",
                                "properties": {
                                    "action": {
                                        "type": "string",
                                        "enum": ["start", "navigate", "capture", "screenshot", "evaluate", "status"],
                                        "description": "Browser action",
                                    },
                                    "url": {"type": "string", "description": "URL for navigate action"},
                                    "script": {"type": "string", "description": "JS for evaluate action"},
                                },
                                "required": ["action"],
                             })
        def browser(args: dict) -> str:
            action = args.get("action", "status")
            script_dir = Path("/root/eigent")

            if action == "start":
                result = subprocess.run(
                    ["node", str(script_dir / "browser-start.js")],
                    capture_output=True, text=True, timeout=15,
                )
                return result.stdout[:1000] or result.stderr[:500] or "Browser started"

            elif action == "navigate":
                url = args.get("url", "")
                if not url:
                    return "Error: url required"
                result = subprocess.run(
                    ["node", str(script_dir / "browser-navigate.js"), url],
                    capture_output=True, text=True, timeout=30,
                )
                return result.stdout[:2000] or result.stderr[:500] or f"Navigated to {url}"

            elif action == "capture":
                # Capture page title/URL via CDP
                result = subprocess.run(
                    ["node", "-e", """
                        const CDP = require('chrome-remote-interface');
                        (async () => {
                            try {
                                const client = await CDP({port: 9222, timeout: 5000});
                                const {Runtime, Page} = client;
                                const title = await Runtime.evaluate({expression: "document.title", returnByValue: true});
                                const url = await Runtime.evaluate({expression: "window.location.href", returnByValue: true});
                                console.log(JSON.stringify({title: title.result.value, url: url.result.value}));
                                await client.close();
                            } catch(e) {
                                console.error(JSON.stringify({error: e.message}));
                                process.exit(1);
                            }
                        })();
                    """],
                    capture_output=True, text=True, timeout=15,
                )
                return result.stdout[:1000] or result.stderr[:200]

            elif action == "screenshot":
                result = subprocess.run(
                    ["node", str(script_dir / "browser-intercept.js"), "--screenshot"],
                    capture_output=True, text=True, timeout=30,
                )
                return result.stdout[:2000] or result.stderr[:500] or "Screenshot captured"

            elif action == "evaluate":
                script = args.get("script", "")
                if not script:
                    return "Error: script required"
                result = subprocess.run(
                    ["node", "-e", f"""
                        const CDP = require('chrome-remote-interface');
                        (async () => {{
                            try {{
                                const client = await CDP({{port: 9222, timeout: 5000}});
                                const {{Runtime}} = client;
                                const r = await Runtime.evaluate({{expression: {repr(script)}, returnByValue: true}});
                                console.log(JSON.stringify(r.result.value));
                                await client.close();
                            }} catch(e) {{
                                console.error(JSON.stringify({{error: e.message}}));
                                process.exit(1);
                            }}
                        }})();
                    """],
                    capture_output=True, text=True, timeout=15,
                )
                return result.stdout[:2000] or result.stderr[:200]

            elif action == "status":
                import urllib.request
                try:
                    r = urllib.request.urlopen("http://localhost:9222/json/version", timeout=5)
                    info = json.loads(r.read())
                    return f"Browser running: {info.get('Browser', 'unknown')} | {info.get('webSocketDebuggerUrl', '')}"
                except Exception as e:
                    return f"Browser not running ({e}). Start with 'browser' action 'start'"

            return f"Unknown browser action: {action}"

        @self.tools.register("skill", description="Load and execute a skill from the skill library",
                             schema={
                                "type": "object",
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "description": "Skill name (e.g. supabase, browser-automation, tdd)",
                                    },
                                },
                                "required": ["name"],
                             })
        def skill(args: dict) -> str:
            name = args.get("name", "")
            skill_dirs = [
                Path("/root/.agents/skills") / name,
                Path("/root/.pi/agent/skills") / name,
                Path("/root/.pi/agent/skills/pi-skills") / name,
            ]
            for skill_dir in skill_dirs:
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    content = skill_file.read_text()
                    return f"# Skill: {name}\n\n{content[:5000]}"
            # Try finding any .md in the skill dir
            for skill_dir in skill_dirs:
                if skill_dir.exists() and skill_dir.is_dir():
                    files = list(skill_dir.glob("*.md"))
                    if files:
                        content = files[0].read_text()
                        return f"# Skill: {name}\n\n{content[:5000]}"
            # List available skills
            available = []
            for base in [Path("/root/.agents/skills"), Path("/root/.pi/agent/skills")]:
                if base.exists():
                    for d in sorted(base.iterdir()):
                        if d.is_dir() and (d / "SKILL.md").exists():
                            available.append(d.name)
            if available:
                return f"Skill '{name}' not found. Available skills:\n" + "\n".join(f"  - {s}" for s in available[:30])
            return f"Skill '{name}' not found. No skills directory accessible."

    def _emit(self, event: AgentEvent):
        for listener in self._event_listeners:
            try:
                listener(event)
            except Exception:
                pass

    def on_event(self, listener: Callable[[AgentEvent], None]):
        self._event_listeners.append(listener)

    def process_query(self, query: str, task_id: str = "",
                      parent_task_id: str = "",
                      stream: bool = True) -> str:
        """
        Process a user query through the full agent loop:
        1. Create task
        2. Recall relevant memories
        3. Build system prompt with context
        4. Call LLM (streaming)
        5. Execute tool calls (mid-turn)
        6. Continue until done
        7. Store result in memory
        8. Return final answer
        """
        # 1. Create or reuse task
        role_enum = AgentRole.SUBORDINATE if self.role == "subordinate" else AgentRole.SUPERIOR
        if not task_id:
            task_id = str(uuid.uuid4())
        task = self.tasks.create_or_reuse_task(
            task_id=task_id,
            query=query,
            role=role_enum,
            parent_task_id=parent_task_id or None,
            metadata={"agent_name": self.name},
        )
        self._emit(AgentEvent.status(task_id, f"Starting task {task_id[:12]}"))
        self.tasks.update_status(task_id, TaskStatus.WORKING)

        # 2. Recall memories
        memory_context = self.memory.inject_context(task_id, query)
        tools_desc = json.dumps(self.tools.list_tools(), indent=2)

        # 3. Build system prompt
        system_content = SYSTEM_PROMPT.format(
            tools_description=tools_desc if self.tools.list_tools() else "No tools available.",
            memory_context=memory_context or "No relevant memories found.",
            role=self.role,
            agent_name=self.name,
            parent="none" if self.role == "superior" else AGENT_NAME,
            children=str(len(self.tmux.list_sessions())),
        )

        # 4. Agent loop
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": query},
        ]

        max_turns = 10
        final_content = ""

        for turn in range(max_turns):
            self._emit(AgentEvent.status(task_id, f"Turn {turn + 1}"))

            # Call LLM
            assistant_msg = self._call_llm_with_streaming(
                messages, task_id, stream=stream
            )

            if not assistant_msg:
                self._emit(AgentEvent.error(task_id, "Empty LLM response"))
                self.tasks.set_error(task_id, "Empty LLM response")
                return "[Agent error: Empty response from LLM]"

            messages.append(assistant_msg)

            # Check for text content
            content = assistant_msg.get("content", "")
            if content:
                final_content = content

            # Check for tool calls
            tool_calls = assistant_msg.get("tool_calls", [])
            if not tool_calls:
                break  # No tools requested — done

            # Execute tool calls
            for tc in tool_calls:
                tc_id = tc.get("id", "")
                fn = tc.get("function", {})
                fn_name = fn.get("name", "")
                try:
                    fn_args = json.loads(fn.get("arguments", "{}"))
                except json.JSONDecodeError:
                    fn_args = {}

                self._emit(AgentEvent.tool_call(task_id, fn_name, fn_args, tc_id))

                # Execute the tool
                result = self.tools.execute(fn_name, fn_args, tool_call_id=tc_id)

                self._emit(AgentEvent.tool_result(
                    task_id, tc_id, fn_name, result.output, result.is_error
                ))

                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": result.output[:5000],
                })

                # Store tool result in memory
                if result.output and not result.is_error:
                    self.memory.store(
                        f"Tool [{fn_name}]: {result.output[:500]}",
                        source=f"tool_result:{fn_name}",
                        agent_name=self.name,
                        task_id=task_id,
                    )

        # 5. Store in memory
        self.memory.store(
            f"Query: {query[:200]}\nAnswer: {final_content[:500]}",
            source="conversation",
            agent_name=self.name,
            task_id=task_id,
        )

        # 6. Finalize
        self.tasks.set_result(task_id, final_content)
        self._emit(AgentEvent.text(task_id, final_content))
        self._emit(AgentEvent.done(task_id))

        return final_content

    def _call_llm_with_streaming(self, messages: list[dict], task_id: str,
                                  stream: bool = True) -> dict:
        """Call LLM with streaming event emission."""
        tool_defs = self.tools.to_llm_format()
        full_content = ""

        def on_stream(data: dict):
            nonlocal full_content
            dt = data.get("type", "")
            if dt == "text_delta":
                delta = data.get("delta", "")
                full_content += delta
                self._emit(AgentEvent.thought_delta(task_id, delta))
                self._emit(AgentEvent.text_delta(task_id, delta))

        try:
            if stream:
                msg = self.llm.chat(
                    messages,
                    tools=tool_defs if tool_defs else None,
                    stream_callback=on_stream,
                )
            else:
                msg = self.llm.chat(
                    messages,
                    tools=tool_defs if tool_defs else None,
                )
            return msg
        except Exception as e:
            self._emit(AgentEvent.error(task_id, f"LLM error: {e}"))
            return {"role": "assistant", "content": f"[Error: {e}]"}

    def get_card(self) -> AgentCard:
        """Return this agent's A2A agent card."""
        children = list(self.tmux.list_sessions())
        return AgentCard(
            name=self.name,
            role=AgentRole(self.role),
            version=AGENT_VERSION,
            capabilities=[t["name"] for t in self.tools.list_tools()],
            description=f"Pi A2A Agent ({self.role})",
            children_urls=[f"tmux://{s['name']}" for s in children],
        )

    def status(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "tools": len(self.tools.list_tools()),
            "tasks": self.tasks.to_dict(),
            "memory": self.memory.status(),
            "subordinates": len(self.tmux.list_sessions()),
        }


# ── CLI Test ────────────────────────────────────────

if __name__ == "__main__":
    import sys
    agent = AgentRuntime()

    if len(sys.argv) > 1 and sys.argv[1] == "query":
        query = " ".join(sys.argv[2:]) or "Say hello"
        result = agent.process_query(query, stream=False)
        print(f"\nResult:\n{result[:2000]}")

    elif len(sys.argv) > 1 and sys.argv[1] == "status":
        print(json.dumps(agent.status(), indent=2, default=str))

    elif len(sys.argv) > 1 and sys.argv[1] == "card":
        print(json.dumps(agent.get_card().to_dict(), indent=2))

    else:
        print("Usage: python3 a2a-agent.py [query|status|card] [text]")
