# Pinned to 3.12 - Django 5.2 on a newer 3.13 patch previously broke admin
# template/form rendering, so don't bump this without re-checking the admin
# in the built image.
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
# Upgrade pip before installing: the pip shipped in the base image has known
# CVEs in its own package-resolution/extraction handling, which run during
# this very install step.
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

RUN chmod +x docker-entrypoint.sh

# Baked into the image at build time (not on every container start) - it
# needs a DJANGO_SETTINGS_MODULE but no real secrets or DB, since SECRET_KEY/
# DATABASE_URL/etc all have safe defaults in config/settings/base.py that
# collectstatic never actually touches.
ENV DJANGO_SETTINGS_MODULE=config.settings.production
# DJANGO_COLLECTSTATIC_ONLY tells production.py to skip its required-env-var
# guard for this one step: collectstatic needs a settings module but touches
# neither SECRET_KEY nor the database. It is set only for this RUN, so a real
# container start still gets the full check.
RUN DJANGO_COLLECTSTATIC_ONLY=1 python manage.py collectstatic --noinput

# Drop root. The image ran as root by default, which meant any RCE-style bug
# in the app - or in a dependency - would have had root inside the container.
# Everything the app does at runtime is either a DB write or an upload to
# Supabase, so it needs no write access to the filesystem; read-only ownership
# of /app is enough. Done after collectstatic so that build step keeps write
# access to staticfiles/.
RUN useradd --system --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Cloud Run injects $PORT (defaults to 8080) and routes traffic there -
# gunicorn must bind to whatever that is, not a hardcoded port. Staying above
# 1024 is also what lets the non-root user bind it.
ENV PORT=8080
EXPOSE 8080

ENTRYPOINT ["./docker-entrypoint.sh"]
