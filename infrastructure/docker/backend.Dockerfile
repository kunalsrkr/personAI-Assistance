FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Optional host SSL-inspection CA (gitignored). Appended so pip trusts PyPI.
COPY infrastructure/docker/certs/ /tmp/extra-certs/
RUN set -e; \
    mkdir -p /usr/local/share/ca-certificates /etc/ssl/certs; \
    if ls /tmp/extra-certs/*.crt >/dev/null 2>&1; then \
      cp /tmp/extra-certs/*.crt /usr/local/share/ca-certificates/; \
      if [ -f /etc/ssl/certs/ca-certificates.crt ]; then \
        cat /tmp/extra-certs/*.crt >> /etc/ssl/certs/ca-certificates.crt; \
      else \
        cat /tmp/extra-certs/*.crt > /etc/ssl/certs/ca-certificates.crt; \
      fi; \
    fi

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir faster-whisper==1.2.0

COPY backend /app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
