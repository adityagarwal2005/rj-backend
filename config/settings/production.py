import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

DEBUG = False

# --- Fail fast on a misconfigured production environment ---
#
# base.py gives SECRET_KEY a development fallback so `manage.py` works out of
# the box. In production that fallback is a serious liability: the value is
# hardcoded and public in this repo, and SECRET_KEY signs session cookies,
# password-reset tokens and (via simplejwt's default) the JWTs themselves.
# Booting with it would let anyone who read this file forge a login for any
# account. Previously a missing or misspelled SECRET_KEY env var would have
# done exactly that, silently and with the site looking perfectly healthy.
#
# Skipped during the image build: the Dockerfile runs collectstatic with
# these settings but deliberately without real secrets, since collectstatic
# touches neither the key nor the database.
if not os.environ.get("DJANGO_COLLECTSTATIC_ONLY"):
    if SECRET_KEY == "unsafe-dev-key-change-me":  # noqa: F405
        raise ImproperlyConfigured(
            "SECRET_KEY is still the development fallback. Set a real, random "
            "SECRET_KEY environment variable before serving production traffic."
        )
    if len(SECRET_KEY) < 50:  # noqa: F405
        raise ImproperlyConfigured(
            "SECRET_KEY is too short for production (needs at least 50 characters)."
        )
    if not ALLOWED_HOSTS:  # noqa: F405
        raise ImproperlyConfigured(
            "ALLOWED_HOSTS is empty. Set it to the host(s) this service is served on."
        )

# Cloud Run (and most reverse proxies) terminate TLS at the load balancer,
# then forward to gunicorn over plain HTTP - so without this, Django can
# never see a request as "already HTTPS" and SECURE_SSL_REDIRECT below
# redirects every single request to HTTPS forever, even ones already on
# HTTPS (an infinite redirect loop). This header is one Cloud Run's proxy
# always sets itself and strips from any client-supplied value first, so
# it can't be spoofed by an external request.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 7  # 1 week, raise once confirmed working
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# EMAIL_BACKEND (Resend via Anymail) is inherited from base.py.

# Whitenoise serves collected static files in production. Override just the
# "staticfiles" backend here rather than setting the legacy STATICFILES_STORAGE
# setting, which Django 5 forbids combining with the STORAGES dict in base.py.
#
# Deliberately NOT using a Manifest-based storage (hashed, cache-busted
# filenames): on Render, collectstatic's manifest ended up referencing hashed
# filenames that didn't match what was actually written to disk (a known
# fragile interaction between Django's multi-pass CSS url() rewriting and
# whitenoise's compression pass), 404ing every admin asset. Plain compressed
# storage skips the hashing step entirely - static files change rarely enough
# here that losing cache-busting is a non-issue, and it removes this whole
# class of bug.
STORAGES["staticfiles"]["BACKEND"] = "whitenoise.storage.CompressedStaticFilesStorage"
