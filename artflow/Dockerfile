FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    ffmpeg \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install the Russian Trusted Root CA so T-Bank (Tinkoff) HTTPS works.
# T-Bank uses the Russian Trusted Root CA, which is not in the default
# CA bundle of the base image.
COPY ops/certs/russian-trusted-root-ca.crt /usr/local/share/ca-certificates/russian-trusted-root-ca.crt
RUN update-ca-certificates

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
# Make Python/httpx use the system CA bundle (which now includes the
# Russian Trusted Root CA) instead of certifi's bundle.
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
