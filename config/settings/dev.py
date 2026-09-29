from config.settings.base import *

SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0

for _alias in DATABASES:
    DATABASES[_alias]["OPTIONS"]["sslmode"] = "prefer"

STORAGES = {
    **STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ),
}

# Nothing runs collectstatic here, so skip WhiteNoise's manifest scan.
WHITENOISE_AUTOREFRESH = True
