#!/bin/bash
# Start all services for the Pi A2A ecosystem
source /root/.bashrc

echo "=== Starting Pi A2A Ecosystem ==="

# 1. Start A2A Agent Server (port 8087)
echo "[1/3] Starting A2A Agent Server..."
cd /root/pi/memory-tool
/usr/bin/python3 a2a-server.py > /tmp/a2a-server.log 2>&1 &
sleep 2
echo "  A2A Agent: http://localhost:8087"

# 2. Start Cloudflare Tunnel
echo "[2/3] Starting Cloudflare Tunnel..."
cloudflared tunnel --url http://localhost:8087 > /tmp/cloudflared.log 2>&1 &
sleep 5
TUNNEL_URL=$(grep -oP 'https://[a-z-]+\.trycloudflare\.com' /tmp/cloudflared.log | head -1)
echo "  Tunnel: $TUNNEL_URL"

# 3. Start Telegram Bot
echo "[3/3] Starting Telegram Bot..."
/usr/bin/python3 tg_a2a_bot.py > /tmp/tg_bot.log 2>&1 &
sleep 2
echo "  Telegram: @PapimashalaBot"

echo ""
echo "=== All services running ==="
echo "  Web UI:     $TUNNEL_URL"
echo "  Telegram:   @PapimashalaBot"
echo "  A2A Agent:  http://localhost:8087"
echo ""
echo "Pi extension: /discover, /tools, /sessions, /skills"
