"""
Cookie-based JWT authentication.

Tokens used to live in localStorage, which any successful XSS could read and
exfiltrate wholesale - the attacker walks away with a working session even
after the page is closed. httpOnly cookies are not readable from JavaScript
at all, so the same XSS can at most make requests as the user while the page
is open, and cannot steal a reusable credential.

This only works because the frontend now reaches the API same-origin,
proxied through Vercel (see vercel.json). Set directly against the Cloud Run
URL, these would be third-party cookies - blocked outright by Safari's ITP
and being phased out in Chrome, which would have logged out every iPhone
user permanently.

CSRF: SameSite=Strict is the protection. A cross-site request simply does
not carry these cookies, so an attacker's forged form or fetch arrives
unauthenticated. That is also why the Authorization-header path below is
kept: it is immune to CSRF by construction and remains the sane option for
any non-browser client.
"""

from rest_framework_simplejwt.authentication import JWTAuthentication

ACCESS_COOKIE = "rt_access"
REFRESH_COOKIE = "rt_refresh"

# The refresh cookie is only ever needed by the auth endpoints, so scope it
# there rather than sending it alongside every product/cart request.
REFRESH_COOKIE_PATH = "/api/auth"


class CookieJWTAuthentication(JWTAuthentication):
    """
    Reads the access token from an httpOnly cookie, falling back to the
    Authorization header.

    The header fallback is deliberate and load-bearing during rollout: it
    means a browser still running the old JavaScript keeps working against
    this backend, so backend and frontend can be deployed in either order
    without a window where every request 401s.
    """

    def authenticate(self, request):
        header_result = super().authenticate(request)
        if header_result is not None:
            return header_result

        raw_token = request.COOKIES.get(ACCESS_COOKIE)
        if not raw_token:
            return None

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token


def _cookie_kwargs(settings):
    """
    Shared cookie flags.

    secure=True everywhere except local HTTP development, since a cookie sent
    over plain HTTP is readable by anything on the network.
    """
    return {
        "httponly": True,
        "secure": not settings.DEBUG,
        "samesite": "Strict",
    }


def set_auth_cookies(response, settings, access: str | None = None, refresh: str | None = None):
    """Attach access/refresh tokens as httpOnly cookies on an outgoing response."""
    kwargs = _cookie_kwargs(settings)
    if access is not None:
        response.set_cookie(
            ACCESS_COOKIE,
            access,
            max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
            path="/",
            **kwargs,
        )
    if refresh is not None:
        response.set_cookie(
            REFRESH_COOKIE,
            refresh,
            max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
            path=REFRESH_COOKIE_PATH,
            **kwargs,
        )
    return response


def clear_auth_cookies(response):
    """Delete both cookies, matching the paths they were set with."""
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
    return response
