FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# VAULT_ROOT must point to the mounted vault volume
ENV VAULT_ROOT=/vault
# Comma-separated directory names to exclude from scanning
ENV EXCLUDE_DIRS=".git,.obsidian,node_modules,.trash"
# Polling interval in seconds for file change detection
# (Docker volume mounts from Windows don't support inotify)
ENV POLL_INTERVAL=5
# REST API configuration
ENV API_ENABLED=true
ENV API_PORT=9400

VOLUME ["/vault"]

EXPOSE 9400

CMD ["python", "src/server.py"]
