#!/usr/bin/env python3
"""
a2a-core — Agent-to-Agent Protocol Types & Task Engine
=========================================================
Defines the protocol types, task lifecycle, event model, and tool registry
that every agent in the hierarchy speaks.

Used by: a2a-memory.py, a2a-tmux.py, a2a-agent.py, a2a-server.py
"""

import json
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional


# ── Enums ───────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING   = "pending"
    WORKING   = "working"
    AWAITING_TOOL = "awaiting_tool"  # waiting for tool result
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"
    DELEGATED = "delegated"  # handed to subordinate


class AgentRole(str, Enum):
    SUPERIOR  = "superior"
    SUBORDINATE = "subordinate"
    PEER      = "peer"


class EventType(str, Enum):
    THOUGHT       = "thought"
    THOUGHT_DELTA = "thought_delta"
    TEXT          = "text"
    TEXT_DELTA    = "text_delta"
    TOOL_CALL      = "tool_call"
    TOOL_RESULT    = "tool_result"
    DELEGATE       = "delegate"
    DELEGATE_RESULT = "delegate_result"
    STATUS         = "status"
    ERROR          = "error"
    DONE           = "done"
    MEMORY_RECALL  = "memory_recall"
    MEMORY_STORE   = "memory_store"


# ── Core Data Types ─────────────────────────────────

@dataclass
class AgentCard:
    """Self-describing agent metadata — A2A discovery."""
    name: str
    role: AgentRole
    version: str = "1.0.0"
    capabilities: list[str] = field(default_factory=list)
    description: str = ""
    agent_url: str = ""
    parent_url: str = ""  # superior agent (if subordinate)
    children_urls: list[str] = field(default_factory=list)  # subordinates

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AgentCard":
        d["role"] = AgentRole(d["role"]) if isinstance(d.get("role"), str) else d.get("role")
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ToolCall:
    """An agent-invoked tool."""
    id: str
    name: str
    arguments: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ToolResult:
    """Result of executing a tool."""
    tool_call_id: str
    tool_name: str
    output: str
    is_error: bool = False
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MemoryEntry:
    """A vectorized memory entry."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    embedding: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = ""  # e.g., "conversation", "tool_result", "delegate_result"
    agent_name: str = ""
    parent_task_id: str = ""  # links to the task that created it

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class AgentMessage:
    """A message in the agent conversation."""

    role: str  # "user", "assistant", "tool_result", "system"
    content: list[dict] = field(default_factory=list)
    # content blocks: {"type": "text", "text": "..."}
    #                 {"type": "thinking", "thinking": "..."}
    #                 {"type": "tool_call", ...}
    #                 {"type": "tool_result", ...}
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_name: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Task:
    """A unit of work in the A2A protocol."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    query: str = ""
    status: TaskStatus = TaskStatus.PENDING
    role: AgentRole = AgentRole.SUPERIOR
    parent_task_id: Optional[str] = None
    subordinate_agent: Optional[str] = None  # which subordinate is handling this
    messages: list[AgentMessage] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["role"] = self.role.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        if isinstance(d.get("status"), str):
            d["status"] = TaskStatus(d["status"])
        if isinstance(d.get("role"), str):
            d["role"] = AgentRole(d["role"])
        if "messages" in d:
            d["messages"] = [AgentMessage(**m) if isinstance(m, dict) else m for m in d["messages"]]
        if "tool_calls" in d:
            d["tool_calls"] = [ToolCall(**tc) if isinstance(tc, dict) else tc for tc in d["tool_calls"]]
        if "tool_results" in d:
            d["tool_results"] = [ToolResult(**tr) if isinstance(tr, dict) else tr for tr in d["tool_results"]]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── Event Stream ────────────────────────────────────

@dataclass
class AgentEvent:
    """An event emitted during agent execution — streamed to clients."""
    type: EventType
    task_id: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_sse(self) -> str:
        """Serialize to Server-Sent Events format."""
        payload = {
            "type": self.type.value if isinstance(self.type, EventType) else self.type,
            "task_id": self.task_id,
            "data": self.data,
            "timestamp": self.timestamp,
        }
        return f"data: {json.dumps(payload)}\n\n"

    @classmethod
    def thought(cls, task_id: str, text: str) -> "AgentEvent":
        return cls(type=EventType.THOUGHT, task_id=task_id, data={"text": text})

    @classmethod
    def thought_delta(cls, task_id: str, delta: str) -> "AgentEvent":
        return cls(type=EventType.THOUGHT_DELTA, task_id=task_id, data={"delta": delta})

    @classmethod
    def text(cls, task_id: str, text: str) -> "AgentEvent":
        return cls(type=EventType.TEXT, task_id=task_id, data={"text": text})

    @classmethod
    def text_delta(cls, task_id: str, delta: str) -> "AgentEvent":
        return cls(type=EventType.TEXT_DELTA, task_id=task_id, data={"delta": delta})

    @classmethod
    def tool_call(cls, task_id: str, tool_name: str, args: dict,
                  tool_call_id: str = "") -> "AgentEvent":
        return cls(type=EventType.TOOL_CALL, task_id=task_id, data={
            "tool_name": tool_name,
            "arguments": args,
            "tool_call_id": tool_call_id or str(uuid.uuid4())[:8],
        })

    @classmethod
    def tool_result(cls, task_id: str, tool_call_id: str, tool_name: str,
                    output: str, is_error: bool = False) -> "AgentEvent":
        return cls(type=EventType.TOOL_RESULT, task_id=task_id, data={
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "output": output[:2000],
            "is_error": is_error,
        })

    @classmethod
    def delegate(cls, task_id: str, subordinate: str, subtask: str) -> "AgentEvent":
        return cls(type=EventType.DELEGATE, task_id=task_id, data={
            "subordinate": subordinate,
            "subtask": subtask,
        })

    @classmethod
    def delegate_result(cls, task_id: str, subordinate: str,
                        result: str) -> "AgentEvent":
        return cls(type=EventType.DELEGATE_RESULT, task_id=task_id, data={
            "subordinate": subordinate,
            "result": result[:2000],
        })

    @classmethod
    def status(cls, task_id: str, text: str) -> "AgentEvent":
        return cls(type=EventType.STATUS, task_id=task_id, data={"text": text})

    @classmethod
    def error(cls, task_id: str, message: str) -> "AgentEvent":
        return cls(type=EventType.ERROR, task_id=task_id, data={"message": message})

    @classmethod
    def done(cls, task_id: str) -> "AgentEvent":
        return cls(type=EventType.DONE, task_id=task_id, data={})

    @classmethod
    def memory_recall(cls, task_id: str, entries: list[dict]) -> "AgentEvent":
        return cls(type=EventType.MEMORY_RECALL, task_id=task_id, data={"entries": entries})

    @classmethod
    def memory_store(cls, task_id: str, text: str) -> "AgentEvent":
        return cls(type=EventType.MEMORY_STORE, task_id=task_id, data={"text": text[:200]})


# ── Tool Registry ───────────────────────────────────

ToolHandler = Callable[[dict[str, Any]], str]

class ToolRegistry:
    """Registry of tools an agent can call — mid-turn execution."""

    def __init__(self):
        self._tools: dict[str, tuple[ToolHandler, str, dict]] = {}

    def register(self, name: str, handler: Optional[ToolHandler] = None,
                 description: str = "", schema: Optional[dict] = None):
        """Register a tool. Works as direct call or decorator."""
        schema = schema or {"type": "object"}
        if handler is not None:
            self._tools[name] = (handler, description, schema)
            return handler
        # Decorator form: return a function that receives the handler
        def decorator(fn: ToolHandler) -> ToolHandler:
            self._tools[name] = (fn, description, schema)
            return fn
        return decorator

    def execute(self, name: str, arguments: dict, tool_call_id: str = "") -> ToolResult:
        start = time.time()
        if name not in self._tools:
            return ToolResult(
                tool_call_id=tool_call_id, tool_name=name,
                output=f"Unknown tool: {name}", is_error=True,
                duration_ms=(time.time() - start) * 1000,
            )
        try:
            handler, _, _ = self._tools[name]
            output = handler(arguments)
            return ToolResult(
                tool_call_id=tool_call_id, tool_name=name, output=str(output),
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return ToolResult(
                tool_call_id=tool_call_id, tool_name=name,
                output=f"Error: {e}", is_error=True,
                duration_ms=(time.time() - start) * 1000,
            )

    def list_tools(self) -> list[dict]:
        return [
            {"name": name, "description": desc, "schema": schema}
            for name, (_, desc, schema) in self._tools.items()
        ]

    def to_llm_format(self) -> list[dict]:
        """Format tools for LLM API (OpenAI function-calling format)."""
        tools = []
        for name, (_, desc, schema) in self._tools.items():
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": schema,
                },
            })
        return tools


# ── Task Manager ───────────────────────────────────

class TaskManager:
    """Manages task lifecycle and hierarchy. Thread-safe."""

    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._event_listeners: list[Callable[[AgentEvent], None]] = []
        self._lock = threading.Lock()

    def create_task(self, query: str, role: AgentRole = AgentRole.SUPERIOR,
                    parent_task_id: Optional[str] = None,
                    subordinate_agent: Optional[str] = None,
                    metadata: Optional[dict] = None) -> Task:
        task = Task(
            query=query,
            role=role,
            parent_task_id=parent_task_id,
            subordinate_agent=subordinate_agent,
            metadata=metadata or {},
        )
        with self._lock:
            self._tasks[task.id] = task
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)

    def create_or_reuse_task(self, task_id: str, query: str,
                              role: AgentRole = AgentRole.SUPERIOR,
                              parent_task_id: Optional[str] = None,
                              subordinate_agent: Optional[str] = None,
                              metadata: Optional[dict] = None) -> Task:
        """Create a task with a specific ID, or return existing if already stored."""
        with self._lock:
            existing = self._tasks.get(task_id)
            if existing:
                existing.query = query
                existing.updated = datetime.now(timezone.utc).isoformat()
                if metadata:
                    existing.metadata.update(metadata)
                return existing
            task = Task(
                id=task_id,
                query=query,
                role=role,
                parent_task_id=parent_task_id,
                subordinate_agent=subordinate_agent,
                metadata=metadata or {},
            )
            self._tasks[task_id] = task
            return task

    def update_status(self, task_id: str, status: TaskStatus):
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = status
                task.updated = datetime.now(timezone.utc).isoformat()

    def add_message(self, task_id: str, message: AgentMessage):
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.messages.append(message)
                task.updated = datetime.now(timezone.utc).isoformat()

    def set_result(self, task_id: str, result: str):
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.result = result
                task.status = TaskStatus.COMPLETED
                task.updated = datetime.now(timezone.utc).isoformat()

    def set_error(self, task_id: str, error: str):
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.error = error
                task.status = TaskStatus.FAILED
                task.updated = datetime.now(timezone.utc).isoformat()

    def get_subtasks(self, parent_task_id: str) -> list[Task]:
        with self._lock:
            return [t for t in self._tasks.values() if t.parent_task_id == parent_task_id]

    def list_tasks(self, status: Optional[TaskStatus] = None,
                   role: Optional[AgentRole] = None) -> list[Task]:
        with self._lock:
            tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        if role:
            tasks = [t for t in tasks if t.role == role]
        return sorted(tasks, key=lambda t: t.created, reverse=True)

    def emit(self, event: AgentEvent):
        """Emit an event to all listeners."""
        with self._lock:
            listeners = list(self._event_listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                pass

    def on_event(self, listener: Callable[[AgentEvent], None]):
        with self._lock:
            self._event_listeners.append(listener)

    def remove_listener(self, listener: Callable[[AgentEvent], None]):
        with self._lock:
            if listener in self._event_listeners:
                self._event_listeners.remove(listener)

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "task_count": len(self._tasks),
                "tasks": {tid: t.to_dict() for tid, t in self._tasks.items()},
            }
