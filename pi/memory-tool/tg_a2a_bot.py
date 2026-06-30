#!/usr/bin/env python3
"""
tg_a2a_bot.py — Telegram ↔ A2A Agent bridge
==============================================
Connects Telegram messages directly to the A2A Agent's chat API.
Uses short polling for reliability on mobile networks.
"""

import json
import os
import sys
import time
import logging
import uuid
import requests
import threading

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TOKEN = os.getenv("TELEGRAM_TOKEN", "")
API_BASE = f"https://api.telegram.org/bot{TOKEN}"
A2A_URL = os.getenv("A2A_URL", "http://localhost:8087")
ALLOWED_CHAT_IDS = set()

POLL_INTERVAL = 0.5
LAST_UPDATE_ID = 0
BACKOFF = 1

logging.basicConfig(level=logging.INFO, format="%(asctime)s [tg-a2a] %(levelname)s: %(message)s")
log = logging.getLogger("tg_a2a_bot")


# ---------------------------------------------------------------------------
# Telegram API
# ---------------------------------------------------------------------------

def tg_get_updates(offset: int = 0) -> list:
    try:
        r = requests.post(f"{API_BASE}/getUpdates", json={"offset": offset, "timeout": 0}, timeout=5)
        if r.status_code == 200 and r.json().get("ok"):
            return r.json()["result"]
    except Exception as e:
        log.warning("getUpdates error: %s", e)
    return []


def tg_send_message(chat_id: str, text: str, parse_mode: str = "HTML", reply_to: int = None) -> bool:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    try:
        r = requests.post(f"{API_BASE}/sendMessage", json=payload, timeout=10)
        return r.status_code == 200 and r.json().get("ok")
    except Exception as e:
        log.warning("sendMessage error: %s", e)
        return False


def tg_send_typing(chat_id: str) -> bool:
    try:
        requests.post(f"{API_BASE}/sendChatAction", json={"chat_id": chat_id, "action": "typing"}, timeout=5)
        return True
    except:
        return False


# ---------------------------------------------------------------------------
# A2A Agent API
# ---------------------------------------------------------------------------

def query_a2a(message: str, chat_id: str) -> str:
    """Send a message to the A2A Agent and get the response via SSE."""
    try:
        resp = requests.post(
            f"{A2A_URL}/a2a/chat",
            json={"message": message},
            stream=True,
            timeout=60,
        )
        if not resp.ok:
            return f"❌ Agent error: {resp.status_code}"

        full_text = ""
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: "):
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    # Handle different event types
                    if chunk.get("type") == "text":
                        content = chunk.get("content", "")
                        full_text += content
                    elif chunk.get("type") == "tool_call":
                        tool_name = chunk.get("tool", "")
                        log.info(f"  🔧 Tool: {tool_name}")
                    elif chunk.get("type") == "tool_result":
                        pass
                    elif chunk.get("type") == "thought":
                        pass
                    elif chunk.get("type") == "status":
                        status = chunk.get("status", "")
                        log.info(f"  📋 Status: {status}")
                except json.JSONDecodeError:
                    pass

        return full_text.strip() or "✅ Done (no text response)"
    except requests.exceptions.Timeout:
        return "⏳ Agent timed out. Try again."
    except requests.exceptions.ConnectionError:
        return "🔌 Agent not reachable. Is the server running?"
    except Exception as e:
        return f"❌ Error: {str(e)[:200]}"


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def handle_message(msg: dict) -> None:
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = msg.get("text", "").strip()
    message_id = msg.get("message_id")
    user = msg.get("from", {})

    if ALLOWED_CHAT_IDS and chat_id not in ALLOWED_CHAT_IDS:
        return
    if not text:
        return

    log.info("From %s (%s): %s", user.get("username", "?"), chat_id, text[:80])

    if text.startswith("/"):
        handle_command(text, chat_id, message_id)
        return

    # Send typing indicator in background
    threading.Thread(target=lambda: (tg_send_typing(chat_id), time.sleep(0.5)), daemon=True).start()

    # Initial "thinking" message
    thinking_msg = tg_send_message(chat_id, "⏳ Thinking...", reply_to=message_id)
    # Get the message ID of the thinking msg to edit later
    # For simplicity, just send the response as a new message

    response = query_a2a(text, chat_id)

    # Truncate if too long for Telegram (4096 chars)
    if len(response) > 4000:
        response = response[:3997] + "..."

    tg_send_message(chat_id, response, reply_to=message_id)


def handle_command(cmd: str, chat_id: str, message_id: int) -> None:
    c = cmd.lower()
    if c == "/start":
        tg_send_message(chat_id, "🤖 <b>Pi A2A Agent Online</b>\n\nSend me any message and I'll process it with the agent.\n\n<b>Commands:</b>\n/status — Check agent status\n/help — This message")
    elif c == "/status":
        try:
            r = requests.get(f"{A2A_URL}/a2a/status", timeout=5)
            if r.ok:
                status = r.json()
                tg_send_message(chat_id, f"✅ <b>Agent Status</b>\n<code>{json.dumps(status, indent=2)}</code>")
            else:
                tg_send_message(chat_id, "❌ Agent returned error")
        except:
            tg_send_message(chat_id, "🔌 Agent not reachable")
    elif c == "/help":
        tg_send_message(chat_id, "Send me any message and I'll forward it to the Pi A2A Agent for processing.")
    else:
        tg_send_message(chat_id, f"Unknown command: {cmd}", reply_to=message_id)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    global LAST_UPDATE_ID, BACKOFF

    if not TOKEN:
        log.critical("TELEGRAM_TOKEN not set!")
        sys.exit(1)

    log.info("=" * 50)
    log.info("TG ↔ A2A Bridge starting")
    log.info(f"A2A URL: {A2A_URL}")

    # Wait for A2A server
    for i in range(30):
        try:
            r = requests.get(f"{A2A_URL}/", timeout=5)
            if r.ok:
                log.info("A2A server reachable!")
                break
        except:
            pass
        if i == 0:
            log.info("Waiting for A2A server...")
        time.sleep(1)

    # Keep trying until connected to Telegram
    while True:
        try:
            info = requests.get(f"{API_BASE}/getMe", timeout=10).json()
            if info.get("ok"):
                bot_name = info["result"]["username"]
                log.info(f"Bot @{bot_name} online")
                break
            log.warning("Bad token, retrying in 5s...")
        except Exception as e:
            log.warning("Cannot reach Telegram: %s", e)
        time.sleep(5)

    log.info("Bridge running. Polling for messages...")

    while True:
        try:
            updates = tg_get_updates(offset=LAST_UPDATE_ID + 1)
            BACKOFF = 1

            for update in updates:
                uid = update.get("update_id", 0)
                if uid > LAST_UPDATE_ID:
                    LAST_UPDATE_ID = uid
                if "callback_query" in update:
                    pass  # No callback queries in basic version
                elif "message" in update:
                    handle_message(update["message"])

        except KeyboardInterrupt:
            log.info("Shutdown")
            break
        except Exception as e:
            log.error("Loop error: %s — backoff %ds", e, BACKOFF)
            time.sleep(BACKOFF)
            BACKOFF = min(BACKOFF * 2, 30)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
