FROM nikolaik/python-nodejs:python3.11-nodejs22

WORKDIR /app

# Install Hermes Agent from GitHub with web+pty extras (required for dashboard)
RUN pip install --quiet --upgrade pip && \
    pip install --quiet "git+https://github.com/NousResearch/hermes-agent.git[web,pty]" && \
    hermes postinstall --non-interactive 2>/dev/null || true

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
