FROM python:3.12-slim

# git is a runtime dependency here: the app pushes notes to the vault repo
RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/data/links.db \
    VAULT_PATH=/data/vault

EXPOSE 8443

CMD ["uvicorn", "tglinks.app:app", "--host", "0.0.0.0", "--port", "8443"]
