from .base import *  # noqa: F401,F403

DEBUG = True

if not ALLOWED_HOSTS:  # noqa: F405
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Print emails to the console unless a real Resend key is configured, so
# developers can opt into testing real delivery locally without any code change.
if not ANYMAIL.get("RESEND_API_KEY"):  # noqa: F405
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
