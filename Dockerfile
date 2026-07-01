FROM nikolaik/python-nodejs:python3.11-nodejs22

WORKDIR /app

# Install Hermes Agent from GitHub with web+pty extras (required for dashboard)
RUN pip install --quiet --upgrade pip && \
    pip install --quiet "hermes-agent[web,pty] @ git+https://github.com/NousResearch/hermes-agent.git" && \
    HERMES_BIN=$(python3 -c "import sysconfig; print(sysconfig.get_path('scripts'))") && \
    echo "Hermes installed to: $HERMES_BIN" && \
    ls -la "$HERMES_BIN/hermes" 2>/dev/null && \
    ln -sf "$HERMES_BIN/hermes" /usr/local/bin/ 2>/dev/null; \
    hermes postinstall --non-interactive 2>/dev/null || true

# Ensure hermes is on PATH
ENV PATH="/usr/local/bin:/root/.local/bin:${PATH}"

# Copy Pi tools into the image
COPY pi /root/pi/

# Copy Numerai pipeline
COPY the-hidden-ledger /root/the-hidden-ledger/

# Copy Hermes config
COPY config.yaml /root/.hermes/config.yaml

# OpenCode provider
ENV DEFAULT_MODEL="deepseek-v4-flash-free"
ENV DEFAULT_PROVIDER="opencode"

# Install Kaggle CLI
RUN pip install --quiet kaggle && mkdir -p /root/.kaggle

# Entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose Hermes Dashboard (web UI)
EXPOSE 8080

CMD /entrypoint.sh
