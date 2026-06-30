#!/usr/bin/env python3
"""
a2a-task-worker — Subordinate Task Worker (runs inside tmux)
==============================================================
Reads .task files from a directory, processes them via the configured
LLM/tools, and writes .result files back.

This is what runs inside each subordinate tmux session.

Usage:
  python3 a2a-task-worker.py --task-dir /tmp/a2a-tasks/worker-1 --agent-name worker-1
"""

import json
import os
import sys
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Import the agent runtime
_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

from a2a_agent import AgentRuntime
from a2a_memory import MemorySystem


def main():
    parser = argparse.ArgumentParser(description="Subordinate task worker")
    parser.add_argument("--task-dir", required=True, help="Directory for .task / .result files")
    parser.add_argument("--agent-name", default="sub-worker", help="Name of this agent")
    args = parser.parse_args()

    task_dir = Path(args.task_dir)
    task_dir.mkdir(parents=True, exist_ok=True)
    agent_name = args.agent_name

    print(f"  [Worker:{agent_name}] Starting task watcher on {task_dir}")
    print(f"  [Worker:{agent_name}] Waiting for .task files...")

    memory = MemorySystem()
    agent = AgentRuntime(name=agent_name, role="subordinate", memory=memory)

    processed = set()

    while True:
        try:
            # Scan for .task files
            for task_file in sorted(task_dir.glob("*.task")):
                if task_file.name in processed:
                    continue

                print(f"  [Worker:{agent_name}] Processing {task_file.name}")
                
                try:
                    payload = json.loads(task_file.read_text())
                except json.JSONDecodeError as e:
                    print(f"  [Worker:{agent_name}] Invalid task file: {e}")
                    processed.add(task_file.name)
                    continue

                task_id = payload.get("id", task_file.stem)
                task_data = payload.get("data", {})

                query = ""
                if isinstance(task_data, str):
                    query = task_data
                elif isinstance(task_data, dict):
                    query = task_data.get("query", task_data.get("message", json.dumps(task_data)))

                # Per-task try/except — a poison task never kills the loop
                try:
                    result = agent.process_query(
                        query=query,
                        task_id=task_id,
                        parent_task_id=payload.get("parent_task_id"),
                    )
                except Exception as e:
                    print(f"  [Worker:{agent_name}] Task {task_id} failed: {e}")
                    result = f"[Worker error: {e}]"

                # Write result file (success or error)
                result_file = task_dir / f"{task_id}.result"
                result_file.write_text(json.dumps({
                    "id": task_id,
                    "result": result,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "agent_name": agent_name,
                }))

                # Clean up task file
                task_file.unlink(missing_ok=True)
                processed.add(task_file.name)

                print(f"  [Worker:{agent_name}] Completed {task_id}")

            time.sleep(1)

        except KeyboardInterrupt:
            print(f"  [Worker:{agent_name}] Shutting down")
            break
        except Exception as e:
            print(f"  [Worker:{agent_name}] Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
