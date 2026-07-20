import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

# ASGI entrypoint is already in place so WebSocket support (e.g. live order
# status updates) can be added later via Django Channels without restructuring.
application = get_asgi_application()
