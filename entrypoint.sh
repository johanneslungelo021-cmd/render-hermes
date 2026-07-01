#!/bin/bash

# Write Kaggle credentials from env vars
if [ -n "$KAGGLE_USERNAME" ] && [ -n "$KAGGLE_KEY" ]; then
  cat > /root/.kaggle/kaggle.json <<EOF
{"username":"$KAGGLE_USERNAME","key":"$KAGGLE_KEY"}
EOF
  chmod 600 /root/.kaggle/kaggle.json
fi

# Wait for potential port conflicts
sleep 2

# Start Hermes Dashboard (web UI for config, sessions, API keys)
echo "Starting Hermes Dashboard on port ${PORT:-8080}..."
exec hermes dashboard --host 0.0.0.0 --port ${PORT:-8080} --insecure --skip-build 2>&1
