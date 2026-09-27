# ADR 0008: Every environment variable is required at startup

Status: Accepted

Date: 2026-09-21

Superseded in part by: [ADR 0017](0017-shipping-fees-are-merchant-data.md), for the
`SHIPPING_FEE_*` variables, which are now the `ShippingSettings` table. The
`decimal` reader went with them.

Supersedes: the "local development without Cloudinary credentials" decision in
`docs/features/media-storage.md`, and the "Khalti settings default to blank, and a
system check enforces them" decision in `docs/features/payments.md`

---

## Context

Configuration reached the application three different ways.

Four variables — `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL`,
`DATABASE_DIRECT_URL` — had no default and raised `ImproperlyConfigured` at import.

Credentials for external services defaulted to empty and were enforced by Django
system checks: `core.E001` for Cloudinary, `payments.E001` for Khalti. That let the
test suite and local development run without a Cloudinary account, a Khalti merchant
account or an SMTP server, which both feature documents recorded as a deliberate
convenience.

Everything else — throttle rates, shipping fees, timeouts, log level — had a default
in `base.py` and could not fail.

Three problems followed from that split, and they are what this decision answers:

- **A default is a decision nobody made.** (Superseded by ADR 0017: the shipping
  fees are no longer environment variables.) `SHIPPING_FEE_OUTSIDE_VALLEY` defaulting
  to `250.00` means a deployment that never set it charges a number chosen by
  whoever wrote the line, in a file nobody reads at deploy time.
- **Malformed values were not caught at boot.** A throttle rate is parsed by DRF
  lazily, on the first request that consults it, and by its first letter only:
  `600/fortnight` raises `KeyError: 'f'` there rather than anywhere near the deploy
  that introduced it, while `600/minutes` and `600/m` are silently accepted as
  minutes. A malformed `KHALTI_BASE_URL` waited for the first customer's payment.
  The pattern is the same in each case — the process started, and the mistake
  surfaced later, somewhere less obviously connected to the cause.
- **`.env.example` drifted.** Eleven variables accumulated in `base.py` without
  reaching it, across four features, because nothing connected the two.

## Decision

**Every environment variable is required, in every environment, and none has a
default.** A variable that is absent, empty, or malformed prevents the settings
module from importing.

`config/settings/strict_env.py` provides `EnvironmentReader`. Every read in
`base.py` goes through it, and `read.raise_for_problems()` at the foot of the file
raises a single `ImproperlyConfigured` listing **every** problem, rather than
failing on the first.

Values are validated, not merely present:

| Reader | Rejects |
| --- | --- |
| `integer`, `decimal` (removed with the `SHIPPING_FEE_*` variables, ADR 0017) | anything that will not parse |
| `flag` | anything that is not a recognised true/false spelling — `env.bool` silently treats `Tru` as false |
| `url` | anything without an `http`/`https` scheme and a host |
| `database` | anything django-environ cannot parse, or that names no database |
| `throttle_rate` | anything but `<number>/<second\|minute\|hour\|day>`, spelled out in full — DRF reads only the first letter, so `600/m` is accepted by it and rejected here |

**No secret reaches the exception text.** The message is printed to the boot log —
in production, Render's — so `strict_env.NEVER_ECHOED` lists the variables whose
value is never quoted back: the two database URLs, `REDIS_URL`, the Django secret
key, the Cloudinary and Khalti secrets, and the SMTP password. A malformed
`DATABASE_URL` reports *"must name a database after the host and port"*, never the
connection string that carries the password. Diagnosing those from the variable's
name alone is the price, and `convention.md` already required it.

Four variables may be empty, because empty is a real choice there:
`DJANGO_CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `EMAIL_HOST_USER` and
`EMAIL_HOST_PASSWORD`. They must still be present.

`config/settings/test.py` populates `os.environ` with obvious fakes before importing
`base.py`, so the suite still runs on a machine with no accounts anywhere. It
assigns them rather than using `setdefault`: a developer whose shell exports the
project's variables would otherwise run the suite against their own configuration,
and a real `DJANGO_SECURE_SSL_REDIRECT` turns every test-client request into a 301.
The database URLs are deliberately absent from that dict, so CI still points the
suite at its own Postgres.

Two variables are outside this rule: `RENDER_EXTERNAL_HOSTNAME`, which is
legitimately absent off Render, and `DJANGO_SETTINGS_MODULE`, which Django reads
before any settings module loads. `convention.md` records both and why.

`core.E001` and `payments.E001` are **removed**. Settings that cannot load without a
credential make a system check that verifies the credential unreachable, and
unreachable validation is worse than none — it reads as a guarantee while doing
nothing.

## Reason

The rule asked for was simple: the application must not start if anything is
missing or misconfigured. A rule with exceptions is a rule people have to remember;
a rule without them is one they can rely on.

The cost is real and was accepted deliberately: a developer cannot run the test
suite or the server without a complete `.env`, and CI must supply one. What is
bought is that **no deployment can be wrong in a way that survives boot**. The
failure modes this replaces were all of the shape "started fine, broke later, in
front of a customer" — a missing Khalti key that surfaces at the first payment, a
shipping fee nobody chose, a throttle rate that silently means something else.

Reporting every problem at once matters more than it looks. Thirty-seven required
variables discovered one deploy at a time is thirty-seven deploys; discovered
together it is one.

## Alternatives considered

### Strict in production only, defaults locally

Keep `DEBUG` as the discriminator, as `payments.E001` already did.

Why it was not chosen: it means the configuration a developer runs is not the
configuration that ships, so the class of bug it catches is exactly the class it
cannot catch — the variable you forgot exists. It also leaves two mechanisms in
place, and the reader has to know which applies to which variable.

### Keep defaults, validate only the format

Cheaper, and it would have caught `600/hr`. Why it was not chosen: it leaves
"nobody set this" indistinguishable from "somebody chose the default", which is
the more common and more expensive mistake.

### A settings schema library (pydantic-settings, django-configurations)

Why it was not chosen: it would add a dependency and a second way to express
settings, to replace about a hundred lines that do exactly what is wanted. The
reader is small enough to read in one sitting, and `convention.md` already requires
every variable to be read in one file.

## Consequences

### Positive

- A misconfigured deployment cannot start, and says everything that is wrong on the
  first attempt.
- `.env.example` is now a working configuration rather than documentation of one,
  and `test_the_documented_example_is_a_working_configuration` proves it.
- Every variable is covered by a test that removes it, and by one that empties it.
  Adding a variable without documenting it fails the suite.
- Malformed values that used to fail at the first request now fail at boot.
- A misconfiguration report can be pasted into an issue without redacting it first.

### Negative

- **`cp .env.example .env` is no longer enough**: the five blanks must be filled
  before anything runs, including the test suite.
- **CI must supply a full environment.** Fakes are fine — `config/settings/test.py`
  shows exactly which — but they must exist.
- A developer who only wants to run the catalogue tests still needs a Khalti value
  in their `.env`. A placeholder works; the strictness is about presence, and only a
  real key can take a payment.
- Every new variable is a breaking change for every deployment until it is set.
  That is the point, and it is why the exception names them all at once.

### Constraints introduced

- Variables are read only through `EnvironmentReader`, and only in `base.py`.
  A bare `env("X", default=...)` reintroduces exactly what this decision removes.
- `config/settings/test.py` must set any new variable, or the suite stops importing.
  `tests/test_settings.py` fails loudly when it does not.
- A variable that may legitimately be empty must be added to
  `strict_env.MAY_BE_EMPTY`, which is a deliberate, greppable list rather than a
  per-call flag.

## Implementation

```text
config/settings/strict_env.py       EnvironmentReader and its validators
config/settings/base.py             every read, and raise_for_problems()
config/settings/test.py             the fake environment, set before import
.env.example                        a complete working configuration
tests/test_settings.py              99 tests: every variable missing, empty,
                                    malformed, and every secret unechoed
apps/core/checks.py                 removed
apps/payments/checks.py             removed
docs/features/media-storage.md      supersedes its local-development decision
docs/features/payments.md           supersedes its blank-defaults decision
```

## Future reconsideration

Revisit if the variable count grows past roughly fifty, at which point a schema
library's per-field declarations start to beat a hundred lines of reader.

Revisit the all-or-nothing rule if it starts pushing developers toward sharing a
`.env` file between people, which would be a worse outcome than the defaults this
replaced. The answer then is a committed `.env.development` of non-secret values,
not a return to defaults in code.
