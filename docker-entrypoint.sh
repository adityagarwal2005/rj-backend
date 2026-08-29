#!/bin/sh
# Runs once per container start, before gunicorn takes over: migrate, then
# bootstrap the admin user, then hand off to the server.
#
# Migrations running here means a burst of simultaneous cold starts could
# theoretically race each other. Low risk for this app's traffic, but if
# it ever bites, move `manage.py migrate` into its own Cloud Run Job run
# once per deploy instead of on every container boot.
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Bootstrapping admin (no-op unless ADMIN_EMAIL/ADMIN_PASSWORD are set)..."
python manage.py bootstrap_admin

echo "Starting gunicorn on port ${PORT}..."
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT}" --workers 2 --threads 4 --timeout 60
