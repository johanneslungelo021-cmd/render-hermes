---
name: tool-discovery
description: Discover and navigate all pi tools, skills, sessions, and configuration. Use /discover for a full system scan, /tools to toggle tools, /sessions to browse sessions, and /skills to list skills.
---

# Tool Discovery & Session Navigation

Discover everything in your pi system: tools, skills, sessions, credentials.

## Commands

| Command | Description |
|---------|-------------|
| `/discover` | Full system scan: all tools, skills, sessions, config |
| `/tools` | Browse and toggle available tools interactively |
| `/sessions` | List all pi sessions with dates and sizes |
| `/skills` | List all available skills with descriptions |

## Custom Tools

These tools are registered by the `tool-discovery` extension:

- **`discover_system`** — Scan the system. Params: `category` (all/tools/skills/sessions/config), `filter` (text search)
- **`list_sessions`** — List sessions. Params: `search`, `limit`
- **`list_skills`** — List skills. Params: `search`
- **`list_tools`** — List tools. Params: `search`, `active_only`

## File Locations

- Extension: `~/.pi/agent/extensions/tool-discovery.ts`
- Sessions: `~/.pi/agent/sessions/--root--/`
- Skills: `~/.pi/agent/skills/` and `~/.agents/skills/`
- Settings: `~/.pi/agent/settings.json`
