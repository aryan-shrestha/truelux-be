import os
from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

from config.settings.strict_env import EnvironmentReader

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ENV_FILE points one command at another deployment's variables instead of .env, e.g.
# importing the catalogue into production from the owner's machine
# (docs/features/catalogue-import.md). Like DJANGO_SETTINGS_MODULE it chooses where
# the settings come from, so it is read before them; convention.md lists the exception.
_env_file = Path(os.environ.get("ENV_FILE") or BASE_DIR / ".env")
if "ENV_FILE" in os.environ and not _env_file.is_file():
    # read_env only warns about a missing file, and the variables it would have set
    # could then come from the shell instead: the wrong database, with no error.
    raise ImproperlyConfigured(f"ENV_FILE names {_env_file}, which does not exist.")

env = environ.Env()
environ.Env.read_env(_env_file)

# Every variable below is required, in every environment, and nothing has a default.
# `read` collects each problem rather than raising on the first, and
# `raise_for_problems()` at the foot of this file reports them together. See ADR 0008.
read = EnvironmentReader(env)

SECRET_KEY = read.text("DJANGO_SECRET_KEY")
DEBUG = read.flag("DJANGO_DEBUG")
ALLOWED_HOSTS = read.string_list("DJANGO_ALLOWED_HOSTS")

CORS_ALLOWED_ORIGINS = read.string_list("DJANGO_CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
# Browsers hide response headers from cross-origin scripts unless they are listed,
# and the storefront quotes the request id in its error messages.
CORS_EXPOSE_HEADERS = ["X-Request-ID"]
CSRF_TRUSTED_ORIGINS = read.string_list("DJANGO_CSRF_TRUSTED_ORIGINS")

SECURE_SSL_REDIRECT = read.flag("DJANGO_SECURE_SSL_REDIRECT")
SECURE_HSTS_SECONDS = read.integer("DJANGO_SECURE_HSTS_SECONDS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "cloudinary_storage",
    "cloudinary",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "django_filters",
    "corsheaders",
    "apps.core",
    "apps.users",
    "apps.catalog",
    "apps.orders",
    "apps.payments",
    "apps.backoffice",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": read.database("DATABASE_URL"),
    # Migrations cannot run over the transaction pooler, which cannot hold the locks
    # and multi-statement state they need. MIRROR keeps the test runner from building
    # a second test database for what is the same server.
    "direct": {
        **read.database("DATABASE_DIRECT_URL"),
        "TEST": {"MIRROR": "default"},
    },
}

# Supabase's transaction pooler multiplexes one server connection across clients,
# which makes server-side cursors and psycopg's prepared statements unusable, and
# makes a Django-side connection pool actively harmful: Supavisor already pools, so
# holding connections open here starves other instances of pooler slots.
for _alias in DATABASES:
    DATABASES[_alias]["CONN_MAX_AGE"] = 0
    DATABASES[_alias]["ATOMIC_REQUESTS"] = False
    DATABASES[_alias].setdefault("OPTIONS", {})
    DATABASES[_alias]["OPTIONS"]["prepare_threshold"] = None
    DATABASES[_alias]["OPTIONS"].setdefault("sslmode", "require")
    DATABASES[_alias]["DISABLE_SERVER_SIDE_CURSORS"] = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "users.User"

# ADR 0014: throttle counters live in Postgres, in a table `createcachetable` builds.
# Local memory would count per process and multiply every limit by the worker count.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    },
}

CLOUDINARY_STORAGE = {
    "CLOUD_NAME": read.text("CLOUDINARY_CLOUD_NAME"),
    "API_KEY": read.text("CLOUDINARY_API_KEY"),
    "API_SECRET": read.text("CLOUDINARY_API_SECRET"),
    "PREFIX": "truelux",
}

STORAGES = {
    "default": {"BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
# Only used where STORAGES["default"] is a filesystem backend; on Render the
# container filesystem is ephemeral and uploads go to Cloudinary instead.
MEDIA_ROOT = BASE_DIR / "media"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_PARSER_CLASSES": ("rest_framework.parsers.JSONParser",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.DefaultLimitOffsetPagination",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.NamespaceVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ("v1",),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": read.throttle_rate("DJANGO_THROTTLE_ANON"),
        "user": read.throttle_rate("DJANGO_THROTTLE_USER"),
        # Browsing needs its own ceiling: one storefront session is a list request,
        # several detail requests and a category request, and behind carrier-grade
        # NAT a whole neighbourhood shares one address. Raising `anon` instead would
        # weaken the order-number lookup, which is an enumeration surface that
        # depends on a low ceiling (ADR 0003).
        "catalog": read.throttle_rate("DJANGO_THROTTLE_CATALOG"),
        # The order-number fallback, kept well under `anon`. Order numbers run in
        # sequence, so this is the one endpoint where guessing is cheap, and the
        # email it also requires is guessable for anyone who knows the customer.
        "order_lookup": read.throttle_rate("DJANGO_THROTTLE_ORDER_LOOKUP"),
        # Checkout writes and holds row locks for the length of its transaction,
        # which makes it more expensive to abuse than any read endpoint here.
        "checkout": read.throttle_rate("DJANGO_THROTTLE_CHECKOUT"),
        # The token endpoints are a password-guessing surface.
        "auth": read.throttle_rate("DJANGO_THROTTLE_AUTH"),
        "admin": read.throttle_rate("DJANGO_THROTTLE_ADMIN"),
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=read.integer("JWT_ACCESS_TOKEN_LIFETIME_MINUTES")),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=read.integer("JWT_REFRESH_TOKEN_LIFETIME_DAYS")),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "SIGNING_KEY": SECRET_KEY,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_AUTHENTICATION_RULE": "apps.users.authentication.is_active_staff",
}

# `make seed-staff` creates this login for the admin app. Outside DEBUG only
# `seed_staff --deploy` uses it, and only while SEED_DEMO_DATA is true (ADR 0015).
DEMO_STAFF_EMAIL = read.text("DEMO_STAFF_EMAIL")
DEMO_STAFF_PASSWORD = read.text("DEMO_STAFF_PASSWORD")
SEED_DEMO_DATA = read.flag("SEED_DEMO_DATA")

SPECTACULAR_SETTINGS = {
    "TITLE": "TrueLux API",
    "DESCRIPTION": "REST API for the TrueLux cosmetics store.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v[0-9]",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
}

EMAIL_BACKEND = read.text("DJANGO_EMAIL_BACKEND")
DEFAULT_FROM_EMAIL = read.text("DJANGO_DEFAULT_FROM_EMAIL")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
EMAIL_HOST = read.text("EMAIL_HOST")
EMAIL_PORT = read.integer("EMAIL_PORT")
EMAIL_HOST_USER = read.text("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = read.text("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = read.flag("EMAIL_USE_TLS")
# ADR 0006 sends email inside the request, so an unresponsive SMTP host would
# otherwise hold a gunicorn worker open indefinitely.
EMAIL_TIMEOUT = read.integer("EMAIL_TIMEOUT")

# The confirmation email links to {STOREFRONT_URL}/orders/<access_token>. https is
# required away from localhost, because that token is a bearer credential under
# ADR 0003 and http would mail it in clear text.
STOREFRONT_URL = read.url("STOREFRONT_URL", require_https=True)

# A district matching neither band pays the outside rate; see checkout.md.
SHIPPING_FEE_INSIDE_VALLEY = read.decimal("SHIPPING_FEE_INSIDE_VALLEY")
SHIPPING_FEE_OUTSIDE_VALLEY = read.decimal("SHIPPING_FEE_OUTSIDE_VALLEY")
KATHMANDU_VALLEY_DISTRICTS = ("kathmandu", "lalitpur", "bhaktapur")

LOG_LEVEL = read.text("DJANGO_LOG_LEVEL")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "apps.core.logging.JSONFormatter"},
    },
    "filters": {
        "redact_uuids": {"()": "apps.core.logging.RedactUUIDs"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        # ERROR only, so 4xx stay quiet -- but a 500 makes Django log the request
        # path, and the order endpoint carries the access_token in it.
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "filters": ["redact_uuids"],
            "propagate": False,
        },
        "apps": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}

# Last, so a misconfigured environment names every problem at once instead of one
# per boot. Nothing above uses a value; they are only assigned.
read.raise_for_problems()
