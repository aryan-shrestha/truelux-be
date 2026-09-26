import os
import tempfile
from pathlib import Path

# Set before base.py is imported: ADR 0008 makes every variable required, and the
# suite must run without a Cloudinary account or an SMTP server. Assigned rather
# than `setdefault`, so a developer's exported .env (a real SSL redirect, say) cannot
# leak into the suite. The database URLs are deliberately absent, so CI and .env
# still choose the Postgres. `.invalid` (RFC 2606) can never resolve.
_TEST_ENVIRONMENT = {
    "DJANGO_SECRET_KEY": "test-secret-key-long-enough-to-sign-jwts",
    "DJANGO_DEBUG": "False",
    "DJANGO_ALLOWED_HOSTS": "testserver,localhost,127.0.0.1",
    "DJANGO_CORS_ALLOWED_ORIGINS": "",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "",
    "DJANGO_SECURE_SSL_REDIRECT": "False",
    "DJANGO_SECURE_HSTS_SECONDS": "0",
    "DJANGO_LOG_LEVEL": "INFO",
    "DJANGO_THROTTLE_ANON": "1000/minute",
    "DJANGO_THROTTLE_USER": "1000/minute",
    "DJANGO_THROTTLE_CATALOG": "1000/minute",
    "DJANGO_THROTTLE_ORDER_LOOKUP": "1000/minute",
    "DJANGO_THROTTLE_CHECKOUT": "1000/minute",
    "DJANGO_THROTTLE_AUTH": "1000/minute",
    "DJANGO_THROTTLE_ADMIN": "1000/minute",
    "JWT_ACCESS_TOKEN_LIFETIME_MINUTES": "15",
    "JWT_REFRESH_TOKEN_LIFETIME_DAYS": "7",
    "CLOUDINARY_CLOUD_NAME": "test-cloud",
    "CLOUDINARY_API_KEY": "test-key",
    "CLOUDINARY_API_SECRET": "test-secret",
    "DJANGO_EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "DJANGO_DEFAULT_FROM_EMAIL": "no-reply@example.invalid",
    "EMAIL_HOST": "smtp.invalid",
    "EMAIL_PORT": "587",
    "EMAIL_HOST_USER": "",
    "EMAIL_HOST_PASSWORD": "",
    "EMAIL_USE_TLS": "True",
    "EMAIL_TIMEOUT": "10",
    "SHIPPING_FEE_INSIDE_VALLEY": "150.00",
    "SHIPPING_FEE_OUTSIDE_VALLEY": "250.00",
    "STOREFRONT_URL": "https://storefront.invalid",
    "DEMO_STAFF_EMAIL": "staff@truelux.invalid",
    "DEMO_STAFF_PASSWORD": "test-staff-password",
    "SEED_DEMO_DATA": "False",
    # The runner builds a fresh test database, which has only `public`.
    "DATABASE_SCHEMA": "public",
}

os.environ.update(_TEST_ENVIRONMENT)

# The database URLs are the one thing a developer must supply: the suite runs
# against a real Postgres, so there is no fake that would work.
from config.settings.base import *

for _alias in DATABASES:
    DATABASES[_alias]["OPTIONS"]["sslmode"] = "prefer"

# Local memory rather than production's DatabaseCache, so the query-count tests
# measure an endpoint's own queries and not the throttle's cache writes.
# apps/core/tests/test_throttling.py covers the database-backed throttle.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-cache",
    },
}

# A temporary root keeps uploads off the working tree and out of Cloudinary, so
# the suite never makes a network call.
MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="truelux-test-media-"))

STORAGES = {
    **STORAGES,
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


# Nothing runs collectstatic here, so skip WhiteNoise's manifest scan.
WHITENOISE_AUTOREFRESH = True
