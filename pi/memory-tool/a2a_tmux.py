#!/usr/bin/env python3
"""
a2a-tmux — Subordinate Agent Manager via tmux
================================================
Spawning, monitoring, and communicating with persistent subordinate
agent sessions in tmux.

Each subordinate is a "worker" running inside a named tmux session.
The superior sends tasks via files (or stdin), the subordinate processes
them, and results are written back.

Architecture:
  tmux session per subordinate
    ├── pane 0: persistent agent loop (reads tasks, executes, writes result)
    └── pane 1: optional monitor/log viewer

Usage:
  from a2a_tmux import TmuxSubordinate
  sub = TmuxSubordinate(name="worker-1")
  sub.spawn()
  sub.send_task("Analyze this data...")
  result = sub.wait_for_result(timeout=120)
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Ensure the memory-tool directory is in the path
_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

from a2a_core import AgentEvent, EventType

TMUX_SOCKET = os.environ.get("TMUX_SOCKET", "")
TASK_DIR = Path(os.environ.get("A2A_TASK_DIR", "/tmp/a2a-tasks"))
TASK_DIR.mkdir(parents=True, exist_ok=True)

AGENT_NAME = os.environ.get("A2A_AGENT_NAME", "pi-agent")


class TmuxSubordinate:
    """A single subordinate agent running in a tmux session."""

    def __init__(self, name: str, agent_type: str = "pi",
                 task_dir: Optional[Path] = None):
        self.name = name
        self.agent_type = agent_type  # "pi", "python", "bash", etc.
        self.task_dir = task_dir or TASK_DIR / name
        self.task_dir.mkdir(parents=True, exist_ok=True)
        self._session_name = f"a2a-sub-{name}"
        self._spawned = False
        self._current_task_id: Optional[str] = None
        self._event_listeners: list = []

    def _tmux_cmd(self, *args: str) -> list[str]:
        base = ["tmux"]
        if TMUX_SOCKET:
            base.extend(["-S", TMUX_SOCKET])
        base.extend(["-L", "a2a-agents"])
        base.extend(args)
        return base

    def _run_tmux(self, *args: str, timeout: int = 5) -> tuple[str, str, int]:
        cmd = self._tmux_cmd(*args)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout, result.stderr, result.returncode

    def spawn(self, startup_cmd: str = "") -> bool:
        """Spawn a tmux session for this subordinate agent."""
        if self._spawned:
            return True

        # Check if tmux session already exists
        stdout, _, rc = self._run_tmux("has-session", "-t", self._session_name)
        if rc == 0:
            self._spawned = True
            return True

        # Create the session detached
        stdout, stderr, rc = self._run_tmux(
            "new-session", "-d", "-s", self._session_name,
            "-x", "120", "-y", "40",
        )
        if rc != 0:
            print(f"  [Tmux] Failed to create session: {stderr}")
            return False

        # Set up the agent loop
        agent_script = self._build_agent_loop()
        self._send_keys(agent_script)

        if startup_cmd:
            self._send_keys(startup_cmd)

        self._spawned = True
        print(f"  [Tmux] Spawned subordinate '{self.name}' in tmux session '{self._session_name}'")
        return True

    def _build_agent_loop(self) -> str:
        """Build the persistent agent loop script for the subordinate."""
        task_dir = str(self.task_dir)
        return (
            f"cd /root/pi/memory-tool && "
            f"python3 a2a-task-worker.py --task-dir {task_dir} --agent-name {self.name}"
        )

    def _send_keys(self, keys: str):
        """Send keys to the tmux session."""
        self._run_tmux("send-keys", "-t", self._session_name, keys, "Enter")

    def send_task(self, task_data: dict) -> Optional[str]:
        """
        Send a task to the subordinate.
        Writes a .task file to the task directory.
        Returns the task_id.
        """
        task_id = str(uuid.uuid4())[:12]
        task_file = self.task_dir / f"{task_id}.task"

        payload = {
            "id": task_id,
            "data": task_data,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "sender": AGENT_NAME,
        }

        task_file.write_text(json.dumps(payload))
        self._current_task_id = task_id

        for listener in self._event_listeners:
            try:
                listener(AgentEvent.delegate(
                    task_id, self.name,
                    json.dumps(task_data)[:200],
                ))
            except Exception:
                pass

        return task_id

    def poll_result(self, task_id: str) -> Optional[dict]:
        """Check if the subordinate has written a result."""
        result_file = self.task_dir / f"{task_id}.result"
        if result_file.exists():
            try:
                data = json.loads(result_file.read_text())
                result_file.unlink(missing_ok=True)  # Clean up
                return data
            except (json.JSONDecodeError, OSError) as e:
                return {"error": str(e)}
        return None

    def wait_for_result(self, task_id: Optional[str] = None,
                         timeout: int = 120, poll_interval: float = 1.0) -> Optional[dict]:
        """Wait for a task result with polling."""
        task_id = task_id or self._current_task_id
        if not task_id:
            return None

        start = time.time()
        while (time.time() - start) < timeout:
            result = self.poll_result(task_id)
            if result is not None:
                # Emit delegate result event
                for listener in self._event_listeners:
                    try:
                        listener(AgentEvent.delegate_result(
                            task_id, self.name,
                            json.dumps(result)[:500],
                        ))
                    except Exception:
                        pass
                return result
            time.sleep(poll_interval)
        return {"error": "timeout", "task_id": task_id}

    def capture_output(self) -> str:
        """Capture what's currently visible in the tmux pane."""
        stdout, _, _ = self._run_tmux("capture-pane", "-t", self._session_name, "-p")
        return stdout

    def send_signal(self, signal: str = "Ctrl-c"):
        """Send a signal to the subordinate process."""
        if signal == "Ctrl-c":
            self._run_tmux("send-keys", "-t", self._session_name, "C-c")
        elif signal == "kill":
            self._run_tmux("kill-session", "-t", self._session_name)
            self._spawned = False

    def kill(self):
        """Kill the tmux session."""
        self._run_tmux("kill-session", "-t", self._session_name)
        self._spawned = False

    def is_alive(self) -> bool:
        """Check if the tmux session is still running."""
        _, _, rc = self._run_tmux("has-session", "-t", self._session_name)
        return rc == 0

    def on_event(self, listener):
        self._event_listeners.append(listener)


class TmuxManager:
    """Manages multiple tmux subordinates."""

    def __init__(self):
        self._subordinates: dict[str, TmuxSubordinate] = {}

    def create(self, name: str, agent_type: str = "python") -> TmuxSubordinate:
        if name in self._subordinates:
            return self._subordinates[name]
        sub = TmuxSubordinate(name=name, agent_type=agent_type)
        self._subordinates[name] = sub
        return sub

    def get(self, name: str) -> Optional[TmuxSubordinate]:
        return self._subordinates.get(name)

    def spawn_all(self) -> dict[str, bool]:
        results = {}
        for name, sub in self._subordinates.items():
            results[name] = sub.spawn()
        return results

    def kill_all(self):
        for sub in self._subordinates.values():
            try:
                sub.kill()
            except Exception:
                pass
        self._subordinates.clear()

    def list_sessions(self) -> list[dict]:
        sessions = []
        try:
            stdout, stderr, rc = self._run_tmux(
                "list-sessions", "-F",
                "#{session_name}:#{session_windows}:#{session_created}",
            )
            if rc == 0:
                for line in stdout.strip().split("\n"):
                    if not line:
                        continue
                    parts = line.split(":")
                    sessions.append({
                        "name": parts[0] if len(parts) > 0 else "",
                        "windows": parts[1] if len(parts) > 1 else "0",
                    })
        except Exception:
            pass
        return sessions


# ── CLI Test ────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    manager = TmuxManager()
    
    if len(sys.argv) > 1 and sys.argv[1] == "spawn":
        name = sys.argv[2] if len(sys.argv) > 2 else "test-worker"
        sub = manager.create(name)
        ok = sub.spawn()
        print(f"{'Spawned' if ok else 'Failed'}: {name}")

    elif len(sys.argv) > 1 and sys.argv[1] == "list":
        for s in manager.list_sessions():
            print(f"  tmux session: {s['name']} ({s['windows']} windows)")

    elif len(sys.argv) > 1 and sys.argv[1] == "kill":
        name = sys.argv[2] if len(sys.argv) > 2 else ""
        if name:
            sub = manager.get(name)
            if sub:
                sub.kill()
                print(f"Killed {name}")
            else:
                print(f"Unknown: {name}")
        else:
            manager.kill_all()
            print("Killed all")

    else:
        print("Usage: python3 a2a-tmux.py [spawn|list|kill] [name]")
