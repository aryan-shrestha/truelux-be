# Deployment

Status: Implemented

Last updated: 2026-11-04

---

## Goal

Run the TrueLux API on the client's cPanel shared host under Passenger, against the
host's PostgreSQL 13 and Cloudinary, one app per environment
([ADR 0022](../decisions/0022-the-api-runs-under-passenger-on-the-cpanel-host.md)).
Two environments, each its own app and database on the same cPanel account:

| Environment | API | Branch | App root | Data |
| --- | --- | --- | --- | --- |
| Dev | `dev.api.trueluxnepal.com` | `dev` | `~/truelux-api-dev` | Demo, seeded on deploy |
| Production | `api.trueluxnepal.com` | `main` | `~/truelux-api-prod` | Real; catalogue imported from the workbook |

Render (`render.yaml`, against Supabase) is suspended. Its configuration stays in
the repository until it is removed.

---

## Scope

What is included in this implementation?

- `passenger_wsgi.py`: the startup file cPanel's Passenger loads
- `make deploy`: the build, run over SSH inside the app's virtualenv
- The runbook below for setting up an environment and deploying to it
- `render.yaml` and the production settings Render needs, until Render is removed
- CI: lint, typecheck, tests and a migrations-are-current check

What is explicitly outside the scope?

- Redis (removed, ADR 0014), a task queue, deploy-on-push, error tracking
- The Next.js storefront and the React admin app, which deploy from their own
  repositories

---

## Context

ADR 0008 requires every variable, and `base.py` reads them from `.env` in the
application root. ADR 0021 pins Django 5.1 for the host's PostgreSQL 13. Images go
to Cloudinary (`media-storage.md`), so the host's disk holds only the code, the
virtualenv and the collected static files, which WhiteNoise serves.

---

## Implemented

- `passenger_wsgi.py` — puts the application root on `sys.path` and exposes
  `config.wsgi.application`, which defaults to `config.settings.production`.
- `Makefile` `deploy` — refuses to run without an active virtualenv, then
  `uv sync --active --frozen --no-dev`, and under `config.settings.production`
  `migrate --database=direct`, `createcachetable --database=direct`,
  `seed_staff --deploy`, `seed_demo --deploy`, `seed_orders --deploy`,
  `collectstatic --noinput`, then `touch tmp/restart.txt`. Every `manage.py` call
  runs `uv run --active --no-sync`, so nothing re-syncs or installs the dev group.
- `.gitignore` — `tmp/`, where Passenger's restart file lives.
- A database URL's own `?sslmode=` wins over the `require` default in `base.py`,
  for a local PostgreSQL without TLS.
- Demo data on deploy (ADR 0015): with `SEED_DEMO_DATA` true, the first deploy to
  an empty database creates the demo staff login, the catalogue (images uploaded to
  Cloudinary) and the order history; every later deploy finds the rows and does
  nothing. With it false the three commands print a line and exit 0.
- `DATABASE_SCHEMA` — every table lives in this schema on both connections, set as
  the libpq startup parameter `-c search_path=<schema>` in `base.py`. It must be a
  lowercase unquoted identifier. On cPanel it is `public`.
- `docker-compose.yml` — local Postgres 13 only, published on host port 5433.
- `.github/workflows/ci.yml` — Postgres 13 service, `make lint`, `make typecheck`,
  `make test`, `makemigrations --check --dry-run`.
- Render, until removed: `render.yaml` — service `truelux-api`, free plan,
  Singapore, `healthCheckPath: /health/`, the same build steps as `make deploy`,
  gunicorn on `$PORT` with 2 workers and a 30 s timeout, 37 variables.
  `config/settings/production.py` appends `RENDER_EXTERNAL_HOSTNAME` to
  `ALLOWED_HOSTS`.
- `config/settings/production.py` — trusts `X-Forwarded-Proto`, exempts `^health/`
  from the SSL redirect, secure cookies and HSTS.

---

## Setting up a cPanel environment

Once per environment. `<app>` is the application root under the home directory,
for example `truelux-api-dev`.

1. **Domain.** Create the subdomain (`dev.api.trueluxnepal.com`) and let AutoSSL
   issue its certificate.
2. **Database.** In *PostgreSQL Databases*, the database and a user with all
   privileges on it. With schema `public` nothing else is needed while the host
   keeps PostgreSQL 13's default, which lets every user create in `public`; if it
   was revoked, `migrate` fails with `permission denied for schema public`.
3. **Mailbox.** In *Email Accounts*, the sending address, for example
   `no-reply@trueluxnepal.com`. *Connect Devices* lists its outgoing server and
   port. Check *Email Deliverability* shows SPF and DKIM as valid, or the mail
   lands in spam.
4. **uv.** Over SSH: `curl -LsSf https://astral.sh/uv/install.sh | sh`, which
   installs to `~/.local/bin`.
5. **Code.** Clone the repository into `~/<app>` and check out the environment's
   branch (`dev` or `main`). A private repository needs a read-only deploy key:
   `ssh-keygen -t ed25519` on the host, the public key added under the GitHub
   repository's *Deploy keys*. One key serves every app on the account.
6. **Python app.** *Setup Python App* → *Create*: Python 3.12, application root
   `<app>`, application URL the subdomain, startup file `passenger_wsgi.py`, entry
   point `application`. **The application root must be outside every document
   root**, `public_html` and the subdomain's own folder included: the web server
   serves any file it finds in a document root, and `.env` would be one. The page then shows the command that activates the app's
   virtualenv, `source ~/virtualenv/<app>/3.12/bin/activate`. Afterwards
   `git status` in `~/<app>` must be clean; if cPanel rewrote `passenger_wsgi.py`,
   `git checkout passenger_wsgi.py`.
7. **Environment.** `cp .env.example .env`, `chmod 600 .env`, and fill in every
   value (see below).
8. **First deploy.** As under *Deploying*.
9. **Check.** `curl https://dev.api.trueluxnepal.com/health/ready/` answers 200
   with `"status": "ready"`, the admin app signs in with `DEMO_STAFF_EMAIL`, and
   `curl https://dev.api.trueluxnepal.com/.env` does not return the file.

### The `.env` of a cPanel environment

Everything in `.env.example` is required (ADR 0008). The values that differ from
the example:

| Variable | Value |
| --- | --- |
| `DATABASE_URL`, `DATABASE_DIRECT_URL` | The same URL: `postgres://<user>:<password>@localhost:5432/<database>`. Add `?sslmode=disable` if the server refuses TLS |
| `DATABASE_SCHEMA` | `public` |
| `DJANGO_SECRET_KEY` | A new random value per environment |
| `DJANGO_ALLOWED_HOSTS` | Dev: `dev.api.trueluxnepal.com`. Production: `api.trueluxnepal.com` |
| `DJANGO_CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | Dev: `https://dev.trueluxnepal.com,https://dev.admin.trueluxnepal.com`. Production: `https://trueluxnepal.com,https://www.trueluxnepal.com,https://admin.trueluxnepal.com` |
| `STOREFRONT_URL` | Dev: `https://dev.trueluxnepal.com`. Production: `https://trueluxnepal.com` |
| `DJANGO_EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS` | `cpcloud.himalayan.host` (the server's host name, which its certificate names), `587`, `True`. Never `465`: see Gotchas |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | The mailbox's address and password |
| `DJANGO_DEFAULT_FROM_EMAIL` | The mailbox's address |
| `SEED_DEMO_DATA` | `true` for the demo, `false` for production before its first deploy |
| `DEMO_STAFF_EMAIL`, `DEMO_STAFF_PASSWORD` in production | Still required (ADR 0008), never used while `SEED_DEMO_DATA` is false |
| `SENTRY_DSN` | The Sentry project's DSN, the same in both apps; empty turns reporting off (`error-tracking.md`) |
| `SENTRY_ENVIRONMENT` | `dev` or `production` |
| `DEMO_STAFF_EMAIL`, `DEMO_STAFF_PASSWORD` | The demo's admin login; the password at least 12 characters |

The rest take the values `render.yaml` sets: `DJANGO_DEBUG=False`,
`DJANGO_SECURE_SSL_REDIRECT=True`, `DJANGO_SECURE_HSTS_SECONDS=31536000` and the
throttle rates. `DJANGO_SETTINGS_MODULE` in `.env` is never honoured
(`convention.md`); `config/wsgi.py` and `make deploy` set production themselves.

---

## Deploying

```bash
source ~/virtualenv/<app>/3.12/bin/activate
cd ~/<app>
git pull
make deploy
```

A variable the new commit requires goes into `.env` before `make deploy`, or the
app fails at import.

---

## Remaining

- **Dev and production are live since 2026-11-04**, and transactional email is
  delivered. Observed on production that day: `https://` serves `/health/ready/`
  as ready with database and cache ok, `http://` redirects with a 301, and `/.env`
  is refused with a 403.
- **Deploys are manual.** Automatic deployment is the next piece of work; it
  amends ADR 0022.
- **Not recorded:** whether the database URLs needed `?sslmode=disable`, and
  where Passenger writes the app's stderr.
- **Dev and production share one Cloudinary folder** (`PREFIX = "truelux"`) if
  they use the same Cloudinary account, so demo and real images sit side by side.
- **Remove Render** (suspended): `render.yaml`, the
  `RENDER_EXTERNAL_HOSTNAME` append and its tests, and the blueprint tests in
  `tests/test_settings.py`, whose parity checks then need `.env.example` as their
  reference. Revisit `SECURE_PROXY_SSL_HEADER` then too: without a proxy in front
  of Passenger nothing strips a client's own `X-Forwarded-Proto`.
- **The pooler settings stay.** `CONN_MAX_AGE=0`, no server-side cursors and no
  prepared statements were for Supabase's pooler; they are harmless against a
  local PostgreSQL, and changing them is its own decision.
- **Migrations run before the restart**, so each must be compatible with the
  release before it, as on Render.
- **No staging environment beyond the demo, and no error tracking.**

---

## Decisions

### Decision: Passenger, with uv syncing into cPanel's virtualenv

[ADR 0022](../decisions/0022-the-api-runs-under-passenger-on-the-cpanel-host.md).

### Decision: the database cache table is built by the deploy

**Decision**

`createcachetable --database=direct` runs after `migrate`, in `make deploy` and in
the Render build.

**Reason**

ADR 0014: the throttle counters live in `django_cache`, which no migration creates.
Without it every throttled request fails; `/health/ready/` reports `cache: error`.

### Decision: the deploy seeds a demo when `SEED_DEMO_DATA` is true

**Decision**

[ADR 0015](../decisions/0015-the-build-seeds-demo-data-when-asked.md). The deploy
runs the three seed commands with `--deploy`. `DEMO_STAFF_EMAIL` and
`DEMO_STAFF_PASSWORD` become the admin login of the demo.

**Reason**

Render's free tier had no shell, so the build was the only place a fresh deploy
could get a catalogue and a staff login. cPanel has a shell, but one command that
always does the same thing is harder to get wrong than a list of steps.

### Decision: the schema is a startup parameter, created by the operator

**Decision**

`DATABASE_SCHEMA` is required (ADR 0008) and passed as `options=-c search_path=<schema>`
on both aliases, with no `public` fallback. Nothing in the app creates the schema.
On cPanel it is `public`, which exists. On Supabase, run `CREATE SCHEMA <schema>;`
before the first deploy, and grant `USAGE, CREATE` on it if the connecting role
does not own it.

**Reason**

Supabase's transaction pooler gives each transaction whichever server connection is
free, so a `SET search_path` on connect would not follow later queries; a startup
parameter is applied to every server connection. `migrate` creates
`django_migrations` before any migration runs, so a migration cannot create the
schema it lives in.

---

## Gotchas

- **Run `make deploy` with the app's virtualenv active.** A bare `uv sync` builds
  `.venv`, which Passenger never reads, and the app keeps running the old
  dependencies. `make deploy` refuses to run without a virtualenv, or with the
  repository's own `.venv`, so it cannot strip a laptop's dev tools or migrate
  whatever a laptop's `.env` points at.
- cPanel's "Run pip install" button is not part of this deploy; `uv.lock` is the
  only dependency list.
- **Every other `make` target is for a laptop.** On the server, plain `make
  superuser` (or `shell`, `seed`, …) runs `uv run` against a new `.venv` with
  `config.settings.dev`. Override both:
  `make <target> DJANGO_SETTINGS_MODULE=config.settings.production MANAGE="uv run --active --no-sync python manage.py"`.
  `make seed` and `make reseed` do not belong on the server at all.
- **`EMAIL_PORT=465` with `EMAIL_USE_TLS=True` hangs.** 465 expects TLS from the
  first byte and STARTTLS waits for a plaintext greeting, so each send waits out
  `EMAIL_TIMEOUT` and logs `email.send_failed` with `SMTPServerDisconnected:
  Connection unexpectedly closed: timed out`, and every checkout takes that much
  longer. Use 587.
- **DNS is on Cloudflare, not cPanel**, so cPanel creates no records for a new
  subdomain or mailbox, and AutoSSL reports "No local authority". Add the `A`
  record (DNS only) in Cloudflare before running AutoSSL. A device that looked
  the name up before the record existed caches the failure for up to 30 minutes
  (the zone's negative TTL).
- **Outbound mail leaves through MailBaby**, the host's relay, so the one SPF record
  must keep `include:spf-c.mailbaby.net`; cPanel's *Email Deliverability* shows
  the record to use. A second SPF record breaks SPF entirely. DKIM
  (`default._domainkey`), DMARC, MX and `mail` are in Cloudflare too. The
  subdomains' "Problems exist" there is expected: nothing sends from them.
- The web server is LiteSpeed. It refuses every path starting with a dot, with
  403, whatever the app root.
- `make deploy`'s `manage.py` calls use `--no-sync`: a plain `uv run` would install
  the dev group back into the virtualenv.
- `DJANGO_CORS_ALLOWED_ORIGINS` may be empty and boots cleanly, but then the
  browser blocks the storefront and the admin app. Both call the API from the
  browser (ADR 0020), so both origins must be listed.
- `/health/` touches nothing; `/health/ready/` checks the database and the cache
  table.
- `Missing staticfiles manifest entry` means `collectstatic` ran without
  `DJANGO_SETTINGS_MODULE=config.settings.production`.
- `no schema has been selected to create in` from `migrate` means the schema in
  `DATABASE_SCHEMA` does not exist in that database.
- For a real shop set `SEED_DEMO_DATA` to `false` before the first deploy.
  Switching it off later keeps whatever was seeded.
- `DEMO_STAFF_PASSWORD` under 12 characters fails the deploy while
  `SEED_DEMO_DATA` is true.
- **Render's free instances block outbound SMTP on 25, 465 and 587.** The connect
  hangs and gunicorn kills the worker mid-checkout, so `render.yaml` sets
  `EMAIL_PORT=2587`, Resend's alternate STARTTLS port. The cPanel host sends through
  its own mail server on 587.
- Render: the free instance sleeps, its region cannot be changed after creation,
  and an existing service keeps an old variable value until the Blueprint is
  re-synced.
- Locally, compose publishes on 5433 so a Homebrew Postgres on 5432 cannot shadow
  the container and run the suite on a version production does not.
- Compose moved from Postgres 16 to 13 (ADR 0021). A volume created by 16 will not
  start under 13: `docker compose down -v` discards it, and its data.

---

## Loading the real catalogue

The client's catalogue is imported from the owner's machine, not by the deploy
([ADR 0016](../decisions/0016-the-real-catalogue-is-imported-from-a-workbook.md);
full runbook in `catalogue-import.md`):

1. Put production's variables in `.env.production` (gitignored, never committed),
   with `SEED_DEMO_DATA=false`.
2. Set `SEED_DEMO_DATA` to `false` in the environment's `.env`, so the deploy does
   not seed demo products into the real shop.
3. `ENV_FILE=.env.production DJANGO_SETTINGS_MODULE=config.settings.production make
   catalogue-import FILE=… IMAGES=… ARGS=--dry-run`, fix what it reports, then run it
   without `--dry-run`.

`ENV_FILE` makes the settings read that file instead of `.env`; a missing file fails
at import. A cPanel database on `localhost` is reachable only from the host, so
against cPanel run the import over SSH in the app root, with the virtualenv active,
or open *Remote PostgreSQL* access for the owner's address first.

---

## Data changes

None.

---

## Permissions

SSH access to the cPanel account controls who can deploy and read `.env`. Render
dashboard access does the same for Render while it remains.

---

## Tests

`tests/test_settings.py`:

- every variable required, secrets never echoed
- `make deploy` runs its steps in the build's order, ending in the restart, and
  runs every `manage.py` call under production settings without re-syncing
- `passenger_wsgi.application` is `config.wsgi.application`
- a database URL's `sslmode` overrides the `require` default
- the blueprint declares exactly the settings' variables, builds under production
  settings, creates the cache table and then seeds
- production security headers and the Render hostname
- `DATABASE_SCHEMA` is validated and becomes both aliases' `search_path`

The `--deploy` paths are tested with the commands: `apps/users/tests/test_auth.py`,
`apps/catalog/tests/test_seed_demo.py`, `apps/orders/tests/test_seed_orders.py`.

---

## Files

```text
passenger_wsgi.py
Makefile
.gitignore
render.yaml
config/settings/production.py
docker-compose.yml
.github/workflows/ci.yml
tests/test_settings.py
```
