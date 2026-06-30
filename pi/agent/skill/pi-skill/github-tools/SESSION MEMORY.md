# GitHub Session

## Token Status

| Item | Value |
|---|---|
| **Status** | ✅ Token is working |
| **User** | johanneslungelo021-cmd |
| **User ID** | 264847169 |
| **Type** | User (private profile) |

## Scopes

The token has very broad access — includes:

- `repo`
- `workflow`
- `admin:org`
- `admin:org_hook`
- `admin:repo_hook`
- `admin:public_key`
- `admin:gpg_key`
- `admin:ssh_signing_key`
- `delete_repo`
- `delete:packages`
- `user`
- `gist`
- `project`
- `codespace`
- `copilot`
- `audit_log`
- `notifications`
- `write:discussion`
- `write:network_configurations`
- `write:packages`

The token authenticates successfully and has extensive permissions.

## Storage Locations

| Location | Purpose |
|---|---|
| `~/.github-token` | Plain file (`chmod 600`) |
| `~/.git-credentials` | Git HTTPS authentication |
| `~/.bashrc` → `$GITHUB_TOKEN` | Environment variable for scripts/shell use |

---

# Hermes Agent

| Item | Value |
|---|---|
| **Version** | v0.16.0 |
| **Language** | Python 3.11.15 |
| **Binary** | `/usr/local/bin/hermes` |
| **Install dir** | `/usr/local/lib/hermes-agent` |
| **Config dir** | `/root/.hermes` |
| **State dir** | `/root/.local/state/hermes` |

---

# Render Deployment

| Item | Value |
|---|---|
| **API Token** | `<redacted>` |
| **Status** | ✅ Token working (tested against `/v1/services`) |
| **Services** | None yet |
| **Account** | Not found |

| Storage Location | Purpose |
|---|---|
| `~/.render-token` | Plain file (`chmod 600`) |
| `~/.bashrc` → `$RENDER_API_KEY` | Environment variable |

# CodeRabbit AI

| Item | Value |
|---|---|
| **API Key** | `cr-6f6e60a35a4d1726c369b753b06700f589a4961d144ea127f737a5bbd3` |
| **Status** | ⚠️ Saved — unable to verify via public API |

| Storage Location | Purpose |
|---|---|
| `~/.coderabbit-token` | Plain file (`chmod 600`) |
| `~/.bashrc` → `$CODERABBIT_API_KEY` | Environment variable |

---

## Deployment Plan

**Agent:** Python-based Hermes Agent ✅ (pushed to `johanneslungelo021-cmd/impact`)

**Target:** Render (Background Worker recommended for bots/agents)

**Steps:**
1. ✅ Push Hermes source to GitHub repo — **Done**
2. Ensure `requirements.txt` and entry point file are present
3. Create Render Web Service or Background Worker
4. Build command: `pip install -r requirements.txt`
5. Start command: `python <entry_point>`
6. Add secrets (API keys) as Render environment variables

---

