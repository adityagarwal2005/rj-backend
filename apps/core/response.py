"""
Standard response envelope used by every endpoint in the project.

Every view should return api_success(...) or api_error(...) instead of a
bare Response(...) so the frontend can rely on one consistent shape:

    { "success": true,  "message": "...", "data": {...} }
    { "success": false, "message": "...", "errors": {...} }
"""

from rest_framework.response import Response


def api_success(data=None, message="Success", status=200):
    return Response({"success": True, "message": message, "data": data}, status=status)


def api_error(message="Something went wrong", errors=None, status=400):
    return Response(
        {"success": False, "message": message, "errors": errors or {}}, status=status
    )
