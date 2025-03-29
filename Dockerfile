FROM python:3.9-slim

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    net-tools \
    dnsutils \
    && rm -rf /var/lib/apt/lists/*

# Requirements will be mounted from the host
RUN --mount=type=bind,source=requirements.txt,target=/app/requirements.txt \
    pip install --no-cache-dir -r requirements.txt

# No need to copy files as they will be mounted as a volume

EXPOSE 5555

USER nobody

CMD ["gunicorn", "--bind", "0.0.0.0:5555", "app:app"] 