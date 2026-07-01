#!/bin/bash
set -uo pipefail

echo "=== Impact AI - Hermes Agent Starting ==="
date -u

PORT=${PORT:-8080}
HERMES_PORT=${HERMES_INTERNAL_PORT:-8081}

# Write Kaggle credentials from env vars
if [ -n "${KAGGLE_USERNAME:-}" ] && [ -n "${KAGGLE_KEY:-}" ]; then
  cat > /root/.kaggle/kaggle.json <<EOF
{"username":"$KAGGLE_USERNAME","key":"$KAGGLE_KEY"}
EOF
  chmod 600 /root/.kaggle/kaggle.json
  echo "✅ Kaggle credentials configured"
fi

# Find hermes command
HERMES_CMD=$(command -v hermes 2>/dev/null || find /usr/local -name hermes -type f 2>/dev/null | head -1)
if [ -z "$HERMES_CMD" ]; then
  echo "ERROR: hermes command not found"
  find / -name hermes -type f 2>/dev/null | head -5
  exit 1
fi
echo "✅ Found hermes at: $HERMES_CMD"
echo "✅ Hermes version: $("$HERMES_CMD" --version 2>&1 || echo 'unknown')"

# If HERMES_PASSWORD is set, inject basic_auth into config.yaml at boot
if [ -n "${HERMES_PASSWORD:-}" ]; then
  python3 - <<EOF
import yaml, os
from plugins.dashboard_auth.basic import hash_password

cfg_path = '/root/.hermes/config.yaml'
with open(cfg_path) as f:
    cfg = yaml.safe_load(f) or {}

cfg.setdefault('dashboard', {})
cfg['dashboard']['host'] = '0.0.0.0'
cfg['dashboard']['port'] = int(os.environ.get('HERMES_INTERNAL_PORT', '8081'))
cfg['dashboard'].setdefault('basic_auth', {})
cfg['dashboard']['basic_auth']['username'] = os.environ.get('HERMES_DASHBOARD_USER', 'admin')
cfg['dashboard']['basic_auth']['password_hash'] = hash_password(os.environ['HERMES_PASSWORD'])

with open(cfg_path, 'w') as f:
    yaml.dump(cfg, f)
EOF
  echo "✅ Dashboard auth configured"
fi

# Start Hermes Gateway in background (ignore failure)
echo "Starting Hermes Gateway..."
"$HERMES_CMD" gateway > /tmp/hermes-gateway.log 2>&1 &
echo "  Gateway PID: $!"

# Test hermes dashboard command first
echo "Testing hermes dashboard command..."
"$HERMES_CMD" dashboard --help > /tmp/hermes-dashboard-help.log 2>&1 || echo "dashboard --help failed"
head -5 /tmp/hermes-dashboard-help.log 2>/dev/null || true

# Start Hermes Dashboard on internal port (not directly exposed)
echo "Starting Hermes Dashboard on internal port $HERMES_PORT..."
"$HERMES_CMD" dashboard --host 0.0.0.0 --port "$HERMES_PORT" --insecure > /tmp/hermes-dashboard.log 2>&1 &
HERMES_DASHBOARD_PID=$!
echo "  Dashboard PID: $HERMES_DASHBOARD_PID"

# Wait briefly for dashboard
sleep 5

# Check if process is still running
if kill -0 $HERMES_DASHBOARD_PID 2>/dev/null; then
  echo "✅ Hermes Dashboard process is running"
else
  echo "⚠️  Hermes Dashboard process died. Logs:"
  cat /tmp/hermes-dashboard.log 2>/dev/null || echo "(no logs)"
fi

# Start health check proxy on PORT (handles Render health checks, proxies to Hermes)
echo "Starting health proxy on port $PORT (→ Hermes on :$HERMES_PORT)..."
exec python3 /app/hermes_proxy.py
