"""
Test settings.

Without this, `manage.py test` inherited DATABASE_URL from .env - which
points at the *production* Supabase Postgres. That meant every test run
created and dropped a `test_postgres` database on the live database server
and pushed several thousand queries across the network to it, which was:

  - slow: a suite that finishes in seconds locally took 20+ minutes, since
    every single query paid a round-trip to Supabase;
  - flaky: a brief network blip aborted the whole run mid-suite with
    "could not receive data from server: No route to host", which reads
    like a code failure but isn't one;
  - risky: DDL (CREATE/DROP DATABASE) executed against the production
    server, and a stray --keepdb left a test database sitting there.

Tests now run against a local Postgres instead. Postgres specifically, not
SQLite: the ordering/payment/stock code relies on select_for_update() for
row locking (see apps.orders.services.create_order_from_cart), which
SQLite does not support and would fail at runtime.

Usage:
    python manage.py test --settings=config.settings.test

Requires a local Postgres (`brew services start postgresql@17`). Override
the connection with TEST_DATABASE_URL if your local setup differs.
"""

import getpass

from .base import *  # noqa: F401,F403

DEBUG = False

# Default to a local Postgres owned by the current OS user, which is how
# Homebrew's postgres initializes its superuser (there is no "postgres"
# role by default on a Homebrew install).
_default_test_db = f"postgres://{getpass.getuser()}@localhost:5432/postgres"
DATABASES = {"default": env.db("TEST_DATABASE_URL", default=_default_test_db)}  # noqa: F405

# Emails are asserted against django.core.mail.outbox, never actually sent.
# base.py wires up the real Resend backend, which would otherwise attempt
# live API calls (and fail) during tests.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# The default PBKDF2 hasher is deliberately slow. Tests create users
# constantly and don't care about hash strength, so this alone takes a
# noticeable chunk off the runtime.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Product images are written to Supabase in production; tests must never
# touch the real bucket, so keep uploads on the local filesystem.
STORAGES["default"] = {"BACKEND": "django.core.files.storage.FileSystemStorage"}  # noqa: F405

# Keep test output clean - the exception handler logs full tracebacks for
# the 500-path tests, which are expected there and just add noise.
LOGGING = {"version": 1, "disable_existing_loggers": True}
