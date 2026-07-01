FROM nikolaik/python-nodejs:python3.11-nodejs22

WORKDIR /app

# Install Hermes Agent via official install script (step 1 from docs)
RUN curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh \
    | bash -s -- --skip-setup --non-interactive --skip-browser 2>&1

# Ensure hermes is on PATH
ENV PATH="/usr/local/bin:/root/.local/bin:${PATH}"

# Verify hermes installed
RUN hermes --version 2>&1 || echo "WARNING: hermes --version failed"

# Copy Hermes config (model providers, toolsets)
COPY config.yaml /root/.hermes/config.yaml

# Copy Pi tools into the image
COPY pi /root/pi/

# Install browser-tools skill dependencies
RUN if [ -f /root/pi/skills/pi-skills/browser-tools/package.json ]; then \
      cd /root/pi/skills/pi-skills/browser-tools && \
      npm install --no-optional --no-fund --no-audit --silent; \
    fi

# Copy Numerai pipeline
COPY the-hidden-ledger /root/the-hidden-ledger/

# OpenCode provider
ENV DEFAULT_MODEL="deepseek-v4-flash-free"
ENV DEFAULT_PROVIDER="opencode"

# Install system deps for entrypoint
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-yaml curl \
    && rm -rf /var/lib/apt/lists/*

# Install Kaggle CLI + Numerai deps
RUN pip install --quiet kaggle pyyaml numpy pandas scipy && mkdir -p /root/.kaggle

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

CMD ["/entrypoint.sh"]
