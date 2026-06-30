FROM nikolaik/python-nodejs:python3.11-nodejs22

WORKDIR /app

# Install Hermes Agent
RUN curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# Add hermes to PATH
ENV PATH="/root/.local/bin:${PATH}"

# Copy Pi tools into the image
COPY pi /root/pi/

# Copy Hermes config
COPY config.yaml /root/.hermes/config.yaml

# OpenCode provider
ENV OPENCODE_API_KEY="sk-BYvG5nYkCJDPNjOejx2ThEcliOYcrUp8QQEqDobcVtncGGT47WQXrKNwopJiF97c"
ENV XIAOMI_API_KEY=""
ENV DEFAULT_MODEL="deepseek-v4-flash-free"
ENV DEFAULT_PROVIDER="opencode"

# Additional Pi tool env vars
ENV MISTRAL_API_KEY="dU3kS44Srh8ovw6GE4H7pYRcqW3DaBXq"

# Telegram
ENV TELEGRAM_BOT_TOKEN="8683400936:AAGJWs75wWYPeoImAoOH6NxtoWY6rtDDopg"

# Expose Hermes Portal (web UI)
EXPOSE 8080

# Use Render's PORT if provided, else 8080
CMD hermes portal --host 0.0.0.0 --port ${PORT:-8080}
