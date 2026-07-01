FROM nikolaik/python-nodejs:python3.11-nodejs22

WORKDIR /app

# Install Hermes Agent via official install script (step 1 from docs)
RUN curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh \
    | bash -s -- --skip-setup --non-interactive --skip-browser 2>&1

# Ensure hermes is on PATH
ENV PATH="/usr/local/bin:/root/.local/bin:${PATH}"

# Fix uv hardlink issue with Docker overlay filesystem
ENV UV_LINK_MODE=copy
ENV UV_NO_CACHE=1

# Verify hermes installed and pre-cache dependencies to avoid runtime errors
RUN hermes --version 2>&1 || echo "WARNING: hermes --version failed"

# Install cua-driver for computer-use toolset
RUN hermes computer-use install 2>&1 || echo "WARNING: cua-driver install failed (not critical)"

# Pre-build Hermes Dashboard web UI so runtime doesn't need npm
RUN cd /usr/local/lib/hermes-agent/web && \
    npm install --no-optional --no-fund --no-audit --silent 2>&1 && \
    npm run build --silent 2>&1 && \
    mkdir -p /usr/local/lib/hermes-agent/hermes_cli && \
    cp -r dist /usr/local/lib/hermes-agent/hermes_cli/web_dist && \
    echo "✅ Web UI built and copied to web_dist"

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

# Install Xvfb (virtual display for computer-use on headless Render)
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11-utils \
    && rm -rf /var/lib/apt/lists/*

# Install system deps for entrypoint
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-yaml curl \
    && rm -rf /var/lib/apt/lists/*

# Install Kaggle CLI + Numerai deps
RUN pip install --quiet kaggle pyyaml numpy pandas scipy && mkdir -p /root/.kaggle

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Copy health check proxy
COPY hermes_proxy.py /app/hermes_proxy.py

EXPOSE 8080

CMD ["/entrypoint.sh"]
