"""
Global DRF exception handler.

Wired up via REST_FRAMEWORK["EXCEPTION_HANDLER"] in settings so every error
response - validation errors, 401s, 403s, 404s, throttling, uncaught 500s -
comes back in the same {"success": false, "message": ..., "errors": {...}}
shape the frontend expects, instead of DRF's raw default format.
"""

import logging

from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("django")


def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is None:
        # Unhandled exception (bug, DB error, etc). Log it and return a
        # generic 500 instead of leaking a stack trace to the client.
        logger.exception("Unhandled exception", exc_info=exc)
        return _error_response("Internal server error", {}, 500)

    detail = response.data

    if isinstance(detail, dict):
        message = detail.get("detail", "Request failed")
        errors = {k: v for k, v in detail.items() if k != "detail"}
    elif isinstance(detail, list):
        message = "Request failed"
        errors = {"non_field_errors": detail}
    else:
        message = str(detail)
        errors = {}

    response.data = {"success": False, "message": str(message), "errors": errors}
    return response


def _error_response(message, errors, status_code):
    from rest_framework.response import Response

    return Response({"success": False, "message": message, "errors": errors}, status=status_code)
