FROM nikolaik/python-nodejs:python3.11-nodejs22

WORKDIR /app

# Install Hermes Agent
RUN curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# Add hermes to PATH
ENV PATH="/root/.local/bin:${PATH}"

# Copy Pi tools into the image
COPY pi /root/pi/

# Copy Numerai pipeline
COPY the-hidden-ledger /root/the-hidden-ledger/

# Copy Hermes config
COPY config.yaml /root/.hermes/config.yaml

# OpenCode provider (set via env on Render)
ENV DEFAULT_MODEL="deepseek-v4-flash-free"
ENV DEFAULT_PROVIDER="opencode"

# Install Kaggle CLI
RUN pip install kaggle && mkdir -p /root/.kaggle

# Entrypoint: write kaggle creds from env vars, then run Hermes
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose Hermes Portal (web UI)
EXPOSE 8080

# Entrypoint writes kaggle creds, then starts Hermes Portal
CMD /entrypoint.sh
