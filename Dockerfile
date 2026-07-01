FROM nikolaik/python-nodejs:python3.11-nodejs22

WORKDIR /app

# Install Hermes Agent via official install script
RUN curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --yes 2>&1 || true

# Ensure hermes is on PATH (root install puts it at /usr/local/bin)
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

CMD /entrypoint.sh
