from datetime import timedelta
from pathlib import Path

import environ

from config.settings.strict_env import EnvironmentReader

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# Every variable below is required, in every environment, and nothing has a default.
# `read` collects each problem rather than raising on the first, and
# `raise_for_problems()` at the foot of this file reports them together. See ADR 0008.
read = EnvironmentReader(env)

SECRET_KEY = read.text("DJANGO_SECRET_KEY")
DEBUG = read.flag("DJANGO_DEBUG")
ALLOWED_HOSTS = read.string_list("DJANGO_ALLOWED_HOSTS")

CORS_ALLOWED_ORIGINS = read.string_list("DJANGO_CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
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

REDIS_URL = read.text("REDIS_URL")

THROTTLE_FALLBACK_CACHE_ALIAS = "throttle_fallback"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    },
    # Throttle counters fall back here when Redis is unreachable, so rate limiting
    # degrades to per-process counting instead of disappearing. Never read directly.
    THROTTLE_FALLBACK_CACHE_ALIAS: {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "throttle-fallback",
    },
}

CLOUDINARY_STORAGE = {
    "CLOUD_NAME": read.text("CLOUDINARY_CLOUD_NAME"),
    "API_KEY": read.text("CLOUDINARY_API_KEY"),
    "API_SECRET": read.text("CLOUDINARY_API_SECRET"),
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
        "apps.core.throttling.ResilientAnonRateThrottle",
        "apps.core.throttling.ResilientUserRateThrottle",
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
        # The payment return is the only unauthenticated endpoint that can change
        # money state. Customers refresh and bookmark it, so the rate has to allow
        # honest repetition while bounding a scripted one.
        "payment_return": read.throttle_rate("DJANGO_THROTTLE_PAYMENT_RETURN"),
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
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Clothing Store API",
    "DESCRIPTION": "REST API for the clothing store backend.",
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

# The storefront root, and the contract between this repository and the Next.js
# one. Three readers: Khalti receives it as `website_url`, the payment return
# redirects the customer to {STOREFRONT_URL}/orders/<access_token>, and the
# confirmation email links to the same page. https is required away from
# localhost, because that token is a bearer credential under ADR 0003 and http
# would mail it in clear text.
STOREFRONT_URL = read.url("STOREFRONT_URL", require_https=True)

# The brand ships by courier at a flat negotiated rate, in two bands. A district
# that matches neither is charged the outside rate: see checkout.md for why that
# direction was chosen. `shipping_fee` is stored on the order, so changing these
# never alters a historical total.
SHIPPING_FEE_INSIDE_VALLEY = read.decimal("SHIPPING_FEE_INSIDE_VALLEY")
SHIPPING_FEE_OUTSIDE_VALLEY = read.decimal("SHIPPING_FEE_OUTSIDE_VALLEY")
KATHMANDU_VALLEY_DISTRICTS = ("kathmandu", "lalitpur", "bhaktapur")

# Khalti's ePayment API (KPG-2). Sandbox and live use different hosts and different
# keys, and a live key against the sandbox host fails in a way that looks like a
# credential problem -- which is why the host is configuration rather than a default.
KHALTI_BASE_URL = read.url("KHALTI_BASE_URL")
KHALTI_SECRET_KEY = read.text("KHALTI_SECRET_KEY")
KHALTI_RETURN_URL = read.url("KHALTI_RETURN_URL")
# ADR 0005 calls Khalti inside the request, so an unresponsive gateway would
# otherwise hold a gunicorn worker open indefinitely. Same reasoning as EMAIL_TIMEOUT.
KHALTI_TIMEOUT = read.integer("KHALTI_TIMEOUT")

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
