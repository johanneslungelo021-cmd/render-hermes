#!/bin/bash

# Write Kaggle credentials from env vars
if [ -n "$KAGGLE_USERNAME" ] && [ -n "$KAGGLE_KEY" ]; then
  cat > /root/.kaggle/kaggle.json <<EOF
{"username":"$KAGGLE_USERNAME","key":"$KAGGLE_KEY"}
EOF
  chmod 600 /root/.kaggle/kaggle.json
fi

# Ensure hermes is on PATH
export PATH="$PATH:/usr/local/bin:/root/.local/bin"

echo "Starting Hermes Dashboard on port ${PORT:-8080}..."
exec hermes dashboard --host 0.0.0.0 --port ${PORT:-8080} --insecure 2>&1
