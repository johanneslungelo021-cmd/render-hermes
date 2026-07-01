#!/bin/bash
set -euo pipefail

# Write Kaggle credentials from env vars
if [ -n "${KAGGLE_USERNAME:-}" ] && [ -n "${KAGGLE_KEY:-}" ]; then
  cat > /root/.kaggle/kaggle.json <<EOF
{"username":"$KAGGLE_USERNAME","key":"$KAGGLE_KEY"}
EOF
  chmod 600 /root/.kaggle/kaggle.json
fi

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
cfg['dashboard']['port'] = int(os.environ.get('PORT', 10000))
cfg['dashboard'].setdefault('basic_auth', {})
cfg['dashboard']['basic_auth']['username'] = os.environ.get('HERMES_DASHBOARD_USER', 'admin')
cfg['dashboard']['basic_auth']['password_hash'] = '${HASH}'

with open(cfg_path, 'w') as f:
    yaml.dump(cfg, f)
EOF
fi

# Find hermes command
HERMES_CMD=$(command -v hermes 2>/dev/null || find /usr/local -name hermes -type f 2>/dev/null | head -1)
if [ -z "$HERMES_CMD" ]; then
  echo "ERROR: hermes command not found"
  exit 1
fi
echo "Found hermes at: $HERMES_CMD"

# Start lightweight health check server on PORT
PORT=${PORT:-8080}
python3 -c "
import http.server, os
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')
    def log_message(self, *a): pass
http.server.HTTPServer(('0.0.0.0', int(os.environ.get('PORT', 8080))), H).serve_forever()
" &
echo "Health check server started on port $PORT"

# Start Hermes Gateway (Telegram via long polling)
echo "Starting Hermes Gateway..."
exec "$HERMES_CMD" gateway 2>&1
