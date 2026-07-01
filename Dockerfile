FROM nikolaik/python-nodejs:python3.11-nodejs22

WORKDIR /app

# Install Hermes Agent from GitHub with web+pty extras (required for dashboard)
RUN git clone --depth 1 https://github.com/NousResearch/hermes-agent.git /tmp/hermes-agent && \
    pip install --quiet --upgrade pip && \
    pip install --quiet "/tmp/hermes-agent[web,pty]" && \
    HERMES_DIR=$(python3 -c "import importlib.util, os; spec=importlib.util.find_spec('hermes'); print(os.path.dirname(spec.origin))") && \
    HERMES_BIN=$(python3 -c "import sysconfig; print(sysconfig.get_path('scripts'))") && \
    ln -sf "$HERMES_BIN/hermes" /usr/local/bin/ && \
    echo "Hermes installed. Web UI at: $HERMES_DIR/web" && \
    echo "Hermes bin: $HERMES_BIN" && \
    rm -rf /tmp/hermes-agent

RUN hermes postinstall --non-interactive 2>/dev/null || true

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

# Install Kaggle CLI + pyyaml (for entrypoint config injection)
RUN pip install --quiet kaggle pyyaml && mkdir -p /root/.kaggle

# Entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose Hermes Dashboard (web UI)
EXPOSE 8080

# Dashboard builds web UI on first launch, then serves
CMD /entrypoint.sh
