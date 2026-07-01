#!/bin/bash
set -euo pipefail

echo "=== Impact AI - Hermes Agent Starting ==="
date -u

PORT=${PORT:-8080}

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
  echo "Searching..."
  find / -name hermes -type f 2>/dev/null | head -5
  exit 1
fi
echo "✅ Found hermes at: $HERMES_CMD"
echo "✅ Hermes version: $("$HERMES_CMD" --version 2>&1 || echo 'unknown')"

# If HERMES_PASSWORD is set, inject basic_auth into config.yaml at boot
if [ -n "${HERMES_PASSWORD:-}" ]; then
  HASH=$(python3 -c "from plugins.dashboard_auth.basic import hash_password; print(hash_password('${HERMES_PASSWORD}'))")
  python3 - <<EOF
import yaml, os

cfg_path = '/root/.hermes/config.yaml'
with open(cfg_path) as f:
    cfg = yaml.safe_load(f) or {}

cfg.setdefault('dashboard', {})
cfg['dashboard']['host'] = '0.0.0.0'
cfg['dashboard']['port'] = int(os.environ.get('PORT', 8080))
cfg['dashboard'].setdefault('basic_auth', {})
cfg['dashboard']['basic_auth']['username'] = os.environ.get('HERMES_DASHBOARD_USER', 'admin')
cfg['dashboard']['basic_auth']['password_hash'] = '${HASH}'

with open(cfg_path, 'w') as f:
    yaml.dump(cfg, f)
EOF
  echo "✅ Dashboard auth configured"
fi

# Start Hermes Gateway in background (Telegram long polling)
echo "Starting Hermes Gateway..."
"$HERMES_CMD" gateway > /tmp/hermes-gateway.log 2>&1 &
echo "  Gateway PID: $!"

# Start Hermes Dashboard as main process
echo "Starting Hermes Dashboard on port $PORT..."
exec "$HERMES_CMD" dashboard --host 0.0.0.0 --port "$PORT" --insecure 2>&1

# If we reach here, something failed
echo "ERROR: Hermes Dashboard exited unexpectedly"
exit 1
