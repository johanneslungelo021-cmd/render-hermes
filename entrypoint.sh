#!/bin/bash

# Write Kaggle credentials from env vars
if [ -n "$KAGGLE_USERNAME" ] && [ -n "$KAGGLE_KEY" ]; then
  cat > /root/.kaggle/kaggle.json <<EOF
{"username":"$KAGGLE_USERNAME","key":"$KAGGLE_KEY"}
EOF
  chmod 600 /root/.kaggle/kaggle.json
fi

# Find hermes command
HERMES_CMD=$(command -v hermes 2>/dev/null || find /usr/local -name hermes -type f 2>/dev/null | head -1)
if [ -z "$HERMES_CMD" ]; then
  echo "ERROR: hermes command not found"
  ls -la /usr/local/bin/ 2>/dev/null
  which python3 2>/dev/null
  exit 1
fi

echo "Found hermes at: $HERMES_CMD"
echo "Starting Hermes Dashboard on port ${PORT:-8080}..."
exec "$HERMES_CMD" dashboard --host 0.0.0.0 --port ${PORT:-8080} --insecure --skip-build 2>&1
