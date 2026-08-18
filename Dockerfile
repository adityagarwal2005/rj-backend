# Pinned to 3.12, matching the Render deploy - Django 5.2 on a newer 3.13
# patch previously broke admin template/form rendering (see render.yaml),
# so don't bump this without re-checking the admin in the built image.
FROM python:3.12-slim

# Fail loudly instead of silently swallowing a broken pip install, and
# don't buffer stdout/stderr so `gcloud run services logs` shows output
# as it happens rather than in delayed chunks.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq5 is the runtime psycopg2-binary needs to actually talk to Postgres;
# without it the wheel imports but every DB connection fails at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN chmod +x docker-entrypoint.sh

# Baked into the image at build time (not on every container start) - it
# needs a DJANGO_SETTINGS_MODULE but no real secrets or DB, since SECRET_KEY/
# DATABASE_URL/etc all have safe defaults in config/settings/base.py that
# collectstatic never actually touches.
ENV DJANGO_SETTINGS_MODULE=config.settings.production
RUN python manage.py collectstatic --noinput

# Cloud Run injects $PORT (defaults to 8080) and routes traffic there -
# gunicorn must bind to whatever that is, not a hardcoded port.
ENV PORT=8080
EXPOSE 8080

ENTRYPOINT ["./docker-entrypoint.sh"]
