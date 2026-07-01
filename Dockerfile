FROM nikolaik/python-nodejs:python3.11-nodejs22

WORKDIR /app

# Install Hermes Agent via official install script
RUN curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-setup --non-interactive 2>&1

# Ensure hermes is on PATH
ENV PATH="/usr/local/bin:/root/.local/bin:${PATH}"

# Pre-build Hermes Dashboard web UI so runtime doesn't need npm
RUN HERMES_WEB_DIR=$(find /usr/local/lib -path '*/hermes/web' -type d 2>/dev/null | head -1) && \
    HERMES_CLI_DIR=$(find /usr/local/lib -path '*/hermes_cli' -type d 2>/dev/null | head -1) && \
    echo "Web dir: $HERMES_WEB_DIR" && \
    echo "CLI dir: $HERMES_CLI_DIR" && \
    if [ -n "$HERMES_WEB_DIR" ] && [ -f "$HERMES_WEB_DIR/package.json" ]; then \
      cd "$HERMES_WEB_DIR" && \
      npm install --no-optional --no-fund --no-audit --silent && \
      NODE_OPTIONS="--max-old-space-size=512" npm run build --silent && \
      if [ -d "dist" ] && [ -n "$HERMES_CLI_DIR" ]; then \
        echo "Copying web dist → $HERMES_CLI_DIR/web_dist" && \
        rm -rf "$HERMES_CLI_DIR/web_dist" && \
        cp -r dist "$HERMES_CLI_DIR/web_dist"; \
      fi; \
    fi

# Copy Pi tools into the image
COPY pi /root/pi/

# Install browser-tools skill dependencies
RUN if [ -f /root/pi/skills/pi-skills/browser-tools/package.json ]; then \
      cd /root/pi/skills/pi-skills/browser-tools && \
      npm install --no-optional --no-fund --no-audit --silent; \
    fi

# Copy Numerai pipeline
COPY the-hidden-ledger /root/the-hidden-ledger/

# Copy Hermes config
COPY config.yaml /root/.hermes/config.yaml

# OpenCode provider
ENV DEFAULT_MODEL="deepseek-v4-flash-free"
ENV DEFAULT_PROVIDER="opencode"

# Install Kaggle CLI + pyyaml + Numerai deps
RUN pip install --quiet kaggle pyyaml numpy pandas scipy && mkdir -p /root/.kaggle

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

CMD /entrypoint.sh
