"""Reads every environment variable, reporting all problems in one exception.

Nothing here has a default. A variable that is absent, empty, or malformed is a
misconfigured deployment, and this module's job is to say so at import rather than
at the first request that happens to need the value.

django-environ raises on the first missing variable, which turns configuring a
deployment into a sequence of one-line discoveries — thirty-seven of them, worst
case. Every read goes through `EnvironmentReader`, which records each problem and
carries on, so one boot names everything that is wrong.

See ADR 0008. Reads still happen only in `base.py`; this module holds the machinery,
not the configuration surface.
"""

import re
from typing import Any
from urllib.parse import urlparse

import environ
from django.core.exceptions import ImproperlyConfigured

# DRF parses a rate as "<number>/<period>" and reads only the period's first letter,
# so "60/fortnight" silently becomes a daily rate. Spelled out here so a typo fails
# at boot rather than quietly changing a limit.
THROTTLE_PERIODS = ("second", "minute", "hour", "day")

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

POSTGRES_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]{0,62}")

TRUE_VALUES = frozenset({"true", "yes", "on", "y", "1"})
FALSE_VALUES = frozenset({"false", "no", "off", "n", "0"})

# Variables whose value must never reach the exception text. A connection string
# carries its password, and `convention.md` puts both on the never-log list -- and
# this exception is printed to the boot log, which in production is Render's.
# Diagnosing these from the variable's name alone is the price.
NEVER_ECHOED = frozenset(
    {
        "DATABASE_URL",
        "DATABASE_DIRECT_URL",
        "DJANGO_SECRET_KEY",
        "CLOUDINARY_API_SECRET",
        "EMAIL_HOST_PASSWORD",
        "DEMO_STAFF_PASSWORD",
    }
)

# Variables where an empty value is a real choice rather than an oversight: a
# deployment may legitimately trust no extra origins, and an SMTP relay may accept
# mail unauthenticated. Every other variable must carry a value.
MAY_BE_EMPTY = frozenset(
    {
        "DJANGO_CORS_ALLOWED_ORIGINS",
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "EMAIL_HOST_USER",
        "EMAIL_HOST_PASSWORD",
    }
)


class EnvironmentReader:
    """Accumulates configuration problems so `raise_for_problems` can report them all.

    Methods avoid the names of the builtins they return, because an annotation in a
    class body resolves against the class namespace: a method called `str` would
    make every later `-> str` mean the method.
    """

    def __init__(self, env: environ.Env) -> None:
        self._env = env
        self._problems: list[str] = []

    def _raw(self, name: str) -> str | None:
        """Returns the raw value, or None when it is absent or unusably empty."""
        try:
            value = str(self._env(name))
        except ImproperlyConfigured:
            self._problems.append(f"{name} is not set")
            return None

        if not value.strip() and name not in MAY_BE_EMPTY:
            self._problems.append(f"{name} is set but empty")
            return None

        return value

    def _reject(self, name: str, reason: str) -> None:
        self._problems.append(f"{name} {reason}")

    def _shown(self, name: str, value: str) -> str:
        """The value as it may appear in the exception, redacted where it is a secret."""
        return "<redacted>" if name in NEVER_ECHOED else repr(value)

    def text(self, name: str) -> str:
        return self._raw(name) or ""

    def integer(self, name: str) -> int:
        value = self._raw(name)
        if value is None:
            return 0
        try:
            return int(value)
        except ValueError:
            self._reject(name, f"must be a whole number, not {self._shown(name, value)}")
            return 0

    def flag(self, name: str) -> bool:
        # Not delegating to env.bool: it treats anything outside its true-strings as
        # False, so `DJANGO_DEBUG=Tru` would silently disable debug rather than fail.
        value = self._raw(name)
        if value is None:
            return False

        lowered = value.strip().lower()
        if lowered in TRUE_VALUES:
            return True
        if lowered in FALSE_VALUES:
            return False

        self._reject(name, f"must be true or false, not {self._shown(name, value)}")
        return False

    def string_list(self, name: str) -> list[str]:
        value = self._raw(name)
        if value is None:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def url(self, name: str, *, require_https: bool = False) -> str:
        value = self._raw(name)
        if value is None:
            return ""

        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            self._reject(name, f"must be an http(s) URL, not {self._shown(name, value)}")
            return ""
        # Loopback is exempt because a credential sent to localhost never crosses a
        # network. Anywhere else, http would put the order's access_token -- a
        # bearer credential under ADR 0003 -- into a link mailed in clear text.
        if require_https and parsed.scheme != "https" and parsed.hostname not in LOOPBACK_HOSTS:
            self._reject(name, f"must be an https URL away from localhost, not {value}")
            return ""
        return value

    def database(self, name: str) -> dict[str, Any]:
        value = self._raw(name)
        if value is None:
            return {}

        try:
            parsed: dict[str, Any] = self._env.db_url_config(value)
        except Exception:  # noqa: BLE001 - any parse failure is the same problem
            self._reject(name, "must be a database URL like postgres://user:pw@host:5432/name")
            return {}

        if not parsed.get("NAME"):
            self._reject(name, "must name a database after the host and port")
            return {}
        return parsed

    def identifier(self, name: str) -> str:
        # Lowercase and unquoted only: the value is spliced into a libpq `options`
        # string, where a space, a comma or a second `-c` would smuggle in further
        # settings or schemas. 63 is Postgres's identifier limit.
        value = self._raw(name)
        if value is None:
            return ""

        if not POSTGRES_IDENTIFIER.fullmatch(value):
            shown = self._shown(name, value)
            self._reject(name, f"must be a lowercase Postgres identifier like truelux, not {shown}")
            return ""
        return value

    def throttle_rate(self, name: str) -> str:
        value = self._raw(name)
        if value is None:
            return "0/second"

        count, _, period = value.partition("/")
        if not count.isdigit() or period not in THROTTLE_PERIODS:
            periods = ", ".join(THROTTLE_PERIODS)
            self._reject(name, f"must be a rate like 60/hour, with a period of {periods}")
            return "0/second"
        return value

    def raise_for_problems(self) -> None:
        if not self._problems:
            return

        listed = "\n".join(f"  - {problem}" for problem in sorted(self._problems))
        raise ImproperlyConfigured(
            f"The environment is not configured correctly:\n{listed}\n\n"
            "Every variable in .env.example is required, in every environment. "
            "Copy it to .env and fill in the blanks."
        )
