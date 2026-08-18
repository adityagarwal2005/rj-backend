from .base import *  # noqa: F401,F403

DEBUG = False

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
