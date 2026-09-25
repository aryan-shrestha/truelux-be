import os

from config.settings.base import *

DEBUG = False

# TLS terminates at Render's proxy, so Django only ever sees plain HTTP and must
# read the forwarded scheme to know a request was secure.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"

# The one variable read outside base.py, and the one exception convention.md
# records. It cannot go through `EnvironmentReader`: ADR 0008's readers require a
# variable to be present, and Render injects this one only on Render. Appended
# rather than assigned, so a custom domain in DJANGO_ALLOWED_HOSTS still works.
#
# Without it every request is a 400 DisallowedHost -- including Render's health
# check, which means the deploy never goes live and the failure reads as an
# application crash rather than a missing hostname.
if _render_hostname := os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS = [*ALLOWED_HOSTS, _render_hostname]

# SecurityMiddleware answers anything it does not consider secure with a 301, and
# a platform health check that arrives without X-Forwarded-Proto would get the
# redirect instead of a 200. The health endpoints expose nothing -- their tests
# assert that a readiness failure leaks no connection string -- so exempting them
# costs nothing and removes a way for a correct deployment to look dead.
SECURE_REDIRECT_EXEMPT = [r"^health/"]
