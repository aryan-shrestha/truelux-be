import importlib
import re
from pathlib import Path

import environ
import pytest
from django.core.exceptions import ImproperlyConfigured

from config.settings import strict_env

BASE_DIR = Path(__file__).resolve().parent.parent

# Matches both the reader's calls and any bare django-environ call, so the guards
# below keep working if the reading style ever changes back.
ENV_CALL = re.compile(r"""(?:read|env)(?:\.\w+)?\(\s*["']([A-Z][A-Z0-9_]*)["']""")

# The blanks `.env.example` leaves for the operator: secrets and account
# identifiers only this deployment's owner can supply.
EXAMPLE_BLANKS = {
    "DJANGO_SECRET_KEY": "settings-test-key",
    "CLOUDINARY_CLOUD_NAME": "test-cloud",
    "CLOUDINARY_API_KEY": "test-key",
    "CLOUDINARY_API_SECRET": "test-secret",
}


def _variables_read_by_settings() -> set[str]:
    source = (BASE_DIR / "config" / "settings" / "base.py").read_text()
    return set(ENV_CALL.findall(source))


def _example_environment() -> dict[str, str]:
    values = {}
    for line in (BASE_DIR / ".env.example").read_text().splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip()
    return values


def _variables_documented() -> set[str]:
    return set(_example_environment())


# `.env.example` with its blanks filled, which is what a correctly configured
# machine looks like. Deriving it from the file rather than restating it means these
# tests also prove the example is a working configuration and not just a list.
COMPLETE_ENVIRONMENT = {**_example_environment(), **EXAMPLE_BLANKS}


def _reload(name: str):
    return importlib.reload(importlib.import_module(name))


@pytest.fixture
def clean_env(monkeypatch):
    # A developer's .env would otherwise repopulate os.environ and mask the
    # missing-variable behaviour this module exists to prove.
    monkeypatch.setattr(environ.Env, "read_env", staticmethod(lambda *a, **kw: None))
    for name in _variables_read_by_settings():
        monkeypatch.delenv(name, raising=False)
    for name, value in COMPLETE_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


def test_the_documented_example_is_a_working_configuration(clean_env):
    # If this fails, `cp .env.example .env` no longer gets a developer running.
    assert _reload("config.settings.base")


# ADR 0008: every variable is required, so these parametrise over all of them rather
# than over a curated list that would drift the moment one was added.
@pytest.mark.parametrize("missing", sorted(_variables_read_by_settings()))
def test_any_missing_variable_fails_at_import(clean_env, missing):
    clean_env.delenv(missing, raising=False)

    with pytest.raises(ImproperlyConfigured, match=missing):
        _reload("config.settings.base")


@pytest.mark.parametrize("empty", sorted(_variables_read_by_settings() - strict_env.MAY_BE_EMPTY))
def test_an_empty_variable_fails_at_import(clean_env, empty):
    clean_env.setenv(empty, "   ")

    with pytest.raises(ImproperlyConfigured, match=empty):
        _reload("config.settings.base")


@pytest.mark.parametrize("name", sorted(strict_env.MAY_BE_EMPTY))
def test_a_variable_that_may_be_empty_is_accepted_empty(clean_env, name):
    # A deployment may legitimately trust no extra origins, and an SMTP relay may
    # accept mail unauthenticated. Those are choices, not oversights.
    clean_env.setenv(name, "")

    assert _reload("config.settings.base")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DJANGO_DEBUG", "Tru"),
        ("SEED_DEMO_DATA", "maybe"),
        ("EMAIL_PORT", "five-eight-seven"),
        ("STOREFRONT_URL", "shop.example.com"),
        ("DATABASE_URL", "not-a-database-url"),
        ("DATABASE_SCHEMA", "truelux,public"),
        ("DATABASE_SCHEMA", "truelux -c statement_timeout=0"),
        ("DATABASE_SCHEMA", "Truelux"),
        ("DJANGO_THROTTLE_CATALOG", "600/fortnight"),
        ("DJANGO_THROTTLE_CATALOG", "lots/hour"),
    ],
)
def test_a_malformed_value_fails_at_import(clean_env, name, value):
    clean_env.setenv(name, value)

    with pytest.raises(ImproperlyConfigured, match=name):
        _reload("config.settings.base")


@pytest.mark.parametrize("name", sorted(strict_env.NEVER_ECHOED))
def test_a_secret_is_never_echoed_into_the_exception(clean_env, name):
    # This exception is printed to the boot log, which in production is Render's.
    # A connection string carries its password; convention.md puts both on the
    # never-log list.
    secret = "s3cret-value-that-must-not-appear"
    clean_env.setenv(name, secret)
    # An unrelated variable is broken so the import fails for every name; otherwise a
    # secret whose probe value is valid would raise nothing and assert nothing.
    clean_env.setenv("DJANGO_THROTTLE_CATALOG", "lots/hour")

    with pytest.raises(ImproperlyConfigured) as exc_info:
        _reload("config.settings.base")

    assert secret not in str(exc_info.value)


@pytest.mark.parametrize(
    ("value", "accepted"),
    [
        ("https://shop.example.com", True),
        ("http://localhost:3000", True),
        ("http://127.0.0.1:3000", True),
        ("http://shop.example.com", False),
    ],
)
def test_storefront_url_must_be_https_away_from_localhost(clean_env, value, accepted):
    # The confirmation email links to {STOREFRONT_URL}/orders/<access_token>, and
    # ADR 0003 makes that token a bearer credential. Over http to a real host it is
    # mailed in clear text. Loopback is exempt: nothing crosses a network.
    clean_env.setenv("STOREFRONT_URL", value)

    if accepted:
        settings = _reload("config.settings.base")
        assert value == settings.STOREFRONT_URL
    else:
        with pytest.raises(ImproperlyConfigured, match="STOREFRONT_URL"):
            _reload("config.settings.base")


def test_a_malformed_database_url_does_not_leak_its_password(clean_env):
    clean_env.setenv("DATABASE_URL", "postgres://user:hunter2@localhost:5432/")

    with pytest.raises(ImproperlyConfigured) as exc_info:
        _reload("config.settings.base")

    message = str(exc_info.value)
    assert "DATABASE_URL" in message
    assert "hunter2" not in message


def test_every_problem_is_reported_in_one_exception(clean_env):
    clean_env.delenv("DJANGO_SECRET_KEY", raising=False)
    clean_env.delenv("DATABASE_URL", raising=False)
    clean_env.setenv("EMAIL_PORT", "not-a-number")
    clean_env.setenv("DJANGO_THROTTLE_ANON", "60/fortnight")

    with pytest.raises(ImproperlyConfigured) as exc_info:
        _reload("config.settings.base")

    # One boot names everything, rather than one variable per deploy cycle.
    message = str(exc_info.value)
    assert "DJANGO_SECRET_KEY is not set" in message
    assert "DATABASE_URL is not set" in message
    assert "EMAIL_PORT must be a whole number" in message
    assert "DJANGO_THROTTLE_ANON must be a rate like 60/hour" in message


def _variables_declared_by_the_blueprint() -> set[str]:
    # Matched rather than parsed: PyYAML is only a transitive dependency.
    source = (BASE_DIR / "render.yaml").read_text()
    return set(re.findall(r"^\s*- key: ([A-Z][A-Z0-9_]*)\s*$", source, re.M))


def test_the_blueprint_declares_every_required_variable():
    # A variable base.py requires but render.yaml omits is a deploy that fails at
    # import with ADR 0008's exception, after a successful build. The blueprint is
    # the only place the production environment is written down.
    assert _variables_read_by_settings() <= _variables_declared_by_the_blueprint()


def test_the_blueprint_declares_nothing_the_settings_ignore():
    # The other direction: a stale key here is a value someone set on Render
    # believing it did something.
    assert _variables_declared_by_the_blueprint() <= _variables_documented()


def test_the_blueprint_runs_the_build_under_production_settings():
    # manage.py falls back to `local`, whose storage writes no staticfiles manifest,
    # so a build without this serves a 500 on every page that uses {% static %}.
    source = (BASE_DIR / "render.yaml").read_text()
    assert re.search(
        r"^\s*- key: DJANGO_SETTINGS_MODULE\s*\n\s*value: config\.settings\.production\s*$",
        source,
        re.M,
    )


def test_production_enables_the_security_headers(clean_env):
    settings = _reload("config.settings.production")

    assert settings.DEBUG is False
    assert settings.SESSION_COOKIE_SECURE is True
    assert settings.CSRF_COOKIE_SECURE is True
    assert settings.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
    assert settings.SECURE_HSTS_PRELOAD is True
    assert settings.SECURE_HSTS_SECONDS > 0
    assert settings.SECURE_SSL_REDIRECT is True
    assert settings.X_FRAME_OPTIONS == "DENY"


def test_production_appends_the_render_hostname(clean_env):
    # Render injects this into every service. Without it every request, including
    # the platform health check, is a 400 DisallowedHost.
    clean_env.setenv("DJANGO_ALLOWED_HOSTS", "shop.example.com")
    clean_env.setenv("RENDER_EXTERNAL_HOSTNAME", "truelux-api.onrender.com")

    # base first: `from base import *` copies values, so reloading production alone
    # would re-run the append against whatever ALLOWED_HOSTS was already imported.
    _reload("config.settings.base")
    settings = _reload("config.settings.production")

    assert settings.ALLOWED_HOSTS == ["shop.example.com", "truelux-api.onrender.com"]


def test_production_leaves_allowed_hosts_alone_off_render(clean_env):
    clean_env.setenv("DJANGO_ALLOWED_HOSTS", "shop.example.com")
    clean_env.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)

    _reload("config.settings.base")
    settings = _reload("config.settings.production")

    assert settings.ALLOWED_HOSTS == ["shop.example.com"]


def test_production_exempts_the_health_endpoints_from_the_ssl_redirect(clean_env):
    # SECURE_SSL_REDIRECT answers anything not already secure with a 301, and a
    # health check that gets a redirect instead of a 200 fails the deploy.
    settings = _reload("config.settings.production")

    assert settings.SECURE_REDIRECT_EXEMPT == [r"^health/"]


def test_production_trusts_the_proxy_forwarded_scheme(clean_env):
    settings = _reload("config.settings.production")

    assert settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")


def test_production_renders_json_only(clean_env):
    settings = _reload("config.settings.production")

    assert settings.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] == (
        "rest_framework.renderers.JSONRenderer",
    )


@pytest.mark.parametrize("alias", ["default", "direct"])
def test_pooler_constraints_are_applied(clean_env, alias):
    settings = _reload("config.settings.base")
    database = settings.DATABASES[alias]

    assert database["CONN_MAX_AGE"] == 0
    assert database["DISABLE_SERVER_SIDE_CURSORS"] is True
    assert database["OPTIONS"]["prepare_threshold"] is None
    # Flipped to True, every view body runs inside a transaction, and ADR 0006's
    # on-commit email and every Cloudinary upload would move inside one.
    assert database["ATOMIC_REQUESTS"] is False


@pytest.mark.parametrize("alias", ["default", "direct"])
def test_database_schema_is_the_connection_search_path(clean_env, alias):
    clean_env.setenv("DATABASE_SCHEMA", "truelux")

    settings = _reload("config.settings.base")

    assert settings.DATABASES[alias]["OPTIONS"]["options"] == "-c search_path=truelux"


def test_the_cache_is_the_database_table_the_build_creates(clean_env):
    settings = _reload("config.settings.base")

    assert settings.CACHES["default"] == {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }


def test_the_blueprint_build_creates_the_cache_table():
    source = (BASE_DIR / "render.yaml").read_text()
    assert "manage.py createcachetable --database=direct" in source


def test_the_blueprint_seeds_demo_data_after_the_cache_table():
    # ADR 0015: the free tier has no shell, so the build is the only place a fresh
    # demo can get its catalogue and staff login.
    source = (BASE_DIR / "render.yaml").read_text()
    assert re.search(r"^\s*- key: SEED_DEMO_DATA\s*\n\s*value: \"true\"\s*$", source, re.M)
    steps = [
        "manage.py createcachetable --database=direct",
        "manage.py seed_staff --deploy",
        "manage.py seed_demo --deploy",
        "manage.py seed_orders --deploy",
    ]
    positions = [source.index(step) for step in steps]
    assert positions == sorted(positions)


def test_seed_demo_data_is_read_as_a_flag(clean_env):
    clean_env.setenv("SEED_DEMO_DATA", "true")

    assert _reload("config.settings.base").SEED_DEMO_DATA is True


def test_direct_alias_mirrors_default_so_tests_build_one_database(clean_env):
    settings = _reload("config.settings.base")

    assert settings.DATABASES["direct"]["TEST"] == {"MIRROR": "default"}


def test_env_example_documents_every_variable_the_settings_read():
    undocumented = _variables_read_by_settings() - _variables_documented()

    assert not undocumented, (
        "These are read by config/settings/base.py but missing from .env.example: "
        f"{', '.join(sorted(undocumented))}. Add them, with a working value."
    )


# Read by Django before any settings module loads, and listed in .env.example only
# so the blueprint guard accepts it. See the exceptions in docs/convention.md.
READ_BEFORE_SETTINGS = {"DJANGO_SETTINGS_MODULE"}


def test_env_example_documents_nothing_the_settings_ignore():
    unread = _variables_documented() - _variables_read_by_settings() - READ_BEFORE_SETTINGS

    assert not unread, (
        "These are in .env.example but read nowhere in config/settings/base.py: "
        f"{', '.join(sorted(unread))}. Remove them, or read them."
    )


def teardown_module():
    # Restore the modules the reloads above mutated so later tests see test settings.
    for name in ("config.settings.base", "config.settings.test"):
        _reload(name)


def test_env_file_chooses_the_file_the_settings_read(clean_env, tmp_path):
    env_file = tmp_path / ".env.production"
    env_file.write_text("")
    read = []
    clean_env.setattr(environ.Env, "read_env", staticmethod(lambda path, **kw: read.append(path)))
    clean_env.setenv("ENV_FILE", str(env_file))

    _reload("config.settings.base")

    assert read == [env_file]


def test_a_missing_env_file_fails_at_import(clean_env, tmp_path):
    clean_env.setenv("ENV_FILE", str(tmp_path / ".env.production"))

    with pytest.raises(ImproperlyConfigured, match="ENV_FILE"):
        _reload("config.settings.base")
