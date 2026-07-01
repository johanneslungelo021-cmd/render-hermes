#!/bin/bash

# Write Kaggle credentials from env vars
if [ -n "$KAGGLE_USERNAME" ] && [ -n "$KAGGLE_KEY" ]; then
  cat > /root/.kaggle/kaggle.json <<EOF
{"username":"$KAGGLE_USERNAME","key":"$KAGGLE_KEY"}
EOF
  chmod 600 /root/.kaggle/kaggle.json
fi

# Find Hermes Python package path to pre-build web UI
HERMES_DIR=$(python3 -c "import importlib.util, os; spec = importlib.util.find_spec('hermes'); print(os.path.dirname(spec.origin))" 2>/dev/null)
if [ -n "$HERMES_DIR" ] && [ -d "$HERMES_DIR/web" ]; then
  echo "Building Hermes Dashboard web UI..."
  cd "$HERMES_DIR/web" && npm install --silent && npm run build --silent 2>/dev/null || echo "Web UI build deferred to first dashboard launch"
fi

# Start Hermes Dashboard
echo "Starting Hermes Dashboard on port ${PORT:-8080}..."
exec hermes dashboard --host 0.0.0.0 --port ${PORT:-8080} --insecure 2>&1
