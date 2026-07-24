"""
Base settings shared by every environment.

Environment-specific overrides live in development.py / production.py.
Nothing in this file should hardcode secrets or environment-specific values -
everything sensitive is pulled from the .env file via django-environ.
"""

from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="unsafe-dev-key-change-me")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# --- Applications ---
# Django apps + third-party apps + our own apps are separated so it's obvious
# at a glance which ones belong to this project (apps.*).
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "anymail",
]

LOCAL_APPS = [
    "apps.core",
    "apps.users",
    "apps.products",
    "apps.orders",
    "apps.payments",
    "apps.notifications",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "users.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serves collected static files in production
    "corsheaders.middleware.CorsMiddleware",  # must sit above CommonMiddleware
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database (Supabase Postgres) ---
DATABASES = {
    "default": env.db(
        "DATABASE_URL", default="postgres://postgres:postgres@localhost:5432/rajwaditukda"
    )
}

# --- Password validation ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- CORS ---
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True

# --- Django REST Framework ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 12,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "auth": "20/min",
    },
}

# --- Simple JWT ---
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env.int("ACCESS_TOKEN_LIFETIME_MINUTES", default=60)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env.int("REFRESH_TOKEN_LIFETIME_DAYS", default=7)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# --- Supabase Storage (S3-compatible) for product images ---
# Product images are uploaded straight to Supabase Storage so the Django
# server never has to hold uploaded files on local disk - this keeps the
# backend stateless and ready for horizontal scaling / containerized deploys.
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

AWS_ACCESS_KEY_ID = env("SUPABASE_STORAGE_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = env("SUPABASE_STORAGE_SECRET_ACCESS_KEY", default="")
AWS_STORAGE_BUCKET_NAME = env("SUPABASE_STORAGE_BUCKET_NAME", default="product-images")
AWS_S3_ENDPOINT_URL = env("SUPABASE_STORAGE_ENDPOINT_URL", default="")
AWS_S3_REGION_NAME = env("SUPABASE_STORAGE_REGION", default="ap-south-1")
AWS_S3_ADDRESSING_STYLE = "path"
AWS_DEFAULT_ACL = "public-read"
AWS_QUERYSTRING_AUTH = False
AWS_S3_FILE_OVERWRITE = False

# Supabase serves publicly-readable files from a different host/path than the
# S3-compatible upload endpoint above (<ref>.storage.supabase.co/storage/v1/s3/...
# is for authenticated S3 API calls only and 403s for a plain browser GET).
# The real public URL pattern is <ref>.supabase.co/storage/v1/object/public/<bucket>/...,
# so django-storages needs to be told to build read URLs from that host instead
# of the upload one - derived automatically from the endpoint URL's project ref.
_supabase_project_ref = (urlparse(AWS_S3_ENDPOINT_URL).hostname or "").split(".")[0]
if _supabase_project_ref:
    AWS_S3_CUSTOM_DOMAIN = f"{_supabase_project_ref}.supabase.co/storage/v1/object/public/{AWS_STORAGE_BUCKET_NAME}"

# --- Email (used by apps/notifications), sent via Resend's HTTP API. ---
# apps/notifications/services.py calls Django's send_mail() as usual - Anymail
# swaps in the Resend backend underneath, so no application code depends on
# the ESP directly and switching providers later is a settings-only change.
EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"
ANYMAIL = {
    "RESEND_API_KEY": env("RESEND_API_KEY", default=""),
}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="RajwadiTukda <no-reply@rajwaditukda.com>")

# --- Payments (prepaid via manual UPI/bank transfer - see apps.payments) ---
# These are shown to customers to complete payment; not secrets, but keep
# them in .env so they're easy to update without a code change.
PAYMENT_UPI_ID = env("PAYMENT_UPI_ID", default="your-upi-id@bank")
PAYMENT_BANK_ACCOUNT_NAME = env("PAYMENT_BANK_ACCOUNT_NAME", default="RajwadiTukda")
PAYMENT_BANK_ACCOUNT_NUMBER = env("PAYMENT_BANK_ACCOUNT_NUMBER", default="0000000000")
PAYMENT_BANK_IFSC = env("PAYMENT_BANK_IFSC", default="XXXX0000000")
PAYMENT_BANK_NAME = env("PAYMENT_BANK_NAME", default="Your Bank Name")
# WhatsApp checkout: full number with country code, no '+' or spaces (e.g. 919999999999).
PAYMENT_WHATSAPP_NUMBER = env("PAYMENT_WHATSAPP_NUMBER", default="910000000000")

# --- Razorpay (optional automated gateway, alongside manual UPI) ---
# Left blank until KYC/signup is done - apps.payments.services only
# registers the Razorpay gateway when a key is actually configured, so this
# is safe to leave empty. RAZORPAY_KEY_ID is also exposed to the frontend
# (it's a publishable identifier, not a secret) to know whether to show the
# "Pay with Razorpay" option at all.
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", default="")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", default="")

# --- Logging ---
# Without this, Django's default logging only emails unhandled 500s to
# ADMINS (unset here) and prints nothing to console - so on a platform like
# Render, which captures stdout/stderr as its log stream, request tracebacks
# would otherwise vanish with no way to see what actually broke.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO"},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}
