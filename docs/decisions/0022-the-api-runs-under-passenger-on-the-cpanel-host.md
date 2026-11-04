# ADR 0022: The API runs under Passenger on the cPanel host

Status: Accepted

Date: 2026-11-04

Supersedes: None. Render stays described in `render.yaml` and `deployment.md` until
the cPanel deployment is live, and is then removed.

---

## Context

The client is moving the API from Render to their cPanel shared host, whose
PostgreSQL 13 already forced Django 5.1 ([ADR 0021](0021-production-runs-postgresql-13-so-django-stays-on-5-1.md)).
The host offers Python 3.12 through cPanel's "Setup Python App", which serves the
app with Passenger and gives it a virtualenv of its own, and SSH access. Each
environment is its own app with its own database: `dev.api.trueluxnepal.com` first,
production later.

Render's build, start command and environment all lived in `render.yaml`. cPanel has
no build step, no blueprint and no gunicorn, and its UI installs dependencies from
`requirements.txt` with pip, which CLAUDE.md rules out.

---

## Decision

- **Passenger loads `passenger_wsgi.py`** at the repository root, which exposes
  `config.wsgi.application`. The app's startup file is `passenger_wsgi.py` and its
  entry point `application`.
- **uv installs from `uv.lock` into the virtualenv cPanel created**: with that
  virtualenv activated, `uv sync --active --frozen --no-dev`. Nothing reads a
  `requirements.txt`, and none exists.
- **`make deploy` is the build**, run over SSH in the app root with the virtualenv
  active, after `git pull`. It runs Render's build steps in Render's order (sync,
  `migrate`, `createcachetable`, the three `--deploy` seeds, `collectstatic`)
  under `config.settings.production`, then touches `tmp/restart.txt` so Passenger
  restarts the app.
- **The environment is a `.env` file in the app root**, mode 600, never committed.
  `base.py` already reads it, so Passenger and every SSH command see the same
  variables. `config/wsgi.py` already defaults to production settings.
- **The database is the host's PostgreSQL on the same machine**, schema `public`,
  one database per environment. There is no pooler, so `DATABASE_URL` and
  `DATABASE_DIRECT_URL` are the same URL.
- **Email goes through the host's own mail server**, from a mailbox created in
  cPanel, over the SMTP settings the settings already read.

---

## Reason

Passenger is what cPanel's Python support is, so there is no gunicorn to run.
Syncing with uv into cPanel's own virtualenv keeps `uv.lock` the only dependency
list, which is the rule CLAUDE.md sets, while Passenger still runs the interpreter
it was configured with. One `.env` file serves both the web process and the
management commands, where variables entered in cPanel's UI would reach only the
web process and leave `make deploy` without a configuration.

---

## Alternatives considered

### Install from a generated `requirements.txt` with cPanel's "Run pip install"

Why it was not chosen: CLAUDE.md forbids pip and `requirements.txt`, and a second
dependency list drifts from `uv.lock` the first time someone forgets to regenerate
it.

### A uv `.venv` in the app root, with `passenger_wsgi.py` re-executing into it

Why it was not chosen: re-executing the interpreter from inside the loader works
only under some Passenger builds, and would hide which Python actually runs. Syncing
into the virtualenv Passenger already uses needs no trick.

### Environment variables in cPanel's "Setup Python App" form

Why it was not chosen: they reach the Passenger process only. Migrations, seeds and
`collectstatic` run over SSH and would need the same values written a second time.

---

## Consequences

### Positive

- `uv.lock` remains the only dependency list, on every platform.
- A deploy is two commands over SSH, and `make deploy` is tested in
  `tests/test_settings.py` like the Render build.

### Negative

- **Deploys are manual.** Nothing deploys on push, and a deploy someone forgets
  leaves the host on the previous commit.
- **Passenger owns processes and timeouts.** The host decides how many processes
  run and how long a request may take. gunicorn's 30 s timeout and two workers no
  longer apply, and are not configurable from the repository.
- **No platform health check.** Nothing restarts the app or alerts anyone if it
  stops answering.
### Constraints introduced

- Every deploy runs `make deploy` with the app's virtualenv active. A bare
  `uv sync` would build `.venv`, which Passenger never reads.
- The application root lies outside every document root. The web server serves any
  file it finds in a document root, `.env` included.
- A new environment variable must be added to every app's `.env` before the
  `git pull` that needs it, or the app fails at import (ADR 0008).

---

## Implementation

```text
passenger_wsgi.py
Makefile (deploy)
.gitignore (tmp/)
.env.example
tests/test_settings.py
docs/features/deployment.md
```

---

## Future reconsideration

If the host's Passenger or LiteSpeed setup is replaced, or the client moves to a host
with a build step or containers, the deploy goes back to a platform configuration
file like `render.yaml`.
