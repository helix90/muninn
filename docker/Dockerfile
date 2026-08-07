FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production
ENV FLASK_APP=run.py

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# All root-level setup in one layer: create user, set ownership,
# make logs dir, write and chmod the entrypoint script.
RUN adduser --disabled-password --gecos '' appuser \
    && mkdir -p /app/logs \
    && chown -R appuser:appuser /app \
    && printf '#!/bin/sh\nset -e\necho "Running database migrations..."\nflask db upgrade\necho "Starting Muninn..."\nexec "$@"\n' \
        > /entrypoint.sh \
    && chmod +x /entrypoint.sh

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Switch to non-root for runtime only — all RUN steps above are root.
USER appuser

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "run.py"]
