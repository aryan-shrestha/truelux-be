# CLAUDE.md

Repository instructions for Claude. Read this before the first edit of a session.

Keep this file short. It contains rules that apply to almost every change. Durable
architecture knowledge, feature state, and decisions belong in `docs/`.

---

## Project

Django REST Framework API service.

- Python 3.12+
- Django 5.x
- Django REST Framework
- PostgreSQL with psycopg 3
- Redis is used for caching and throttling only.
- There is **no Celery or task queue**. Do not add, stub, or introduce one.
- `uv` manages dependencies, the virtual environment, and command execution.
- Do not use pip, Poetry, or `requirements.txt`.

---

## Commands

Use the repository Makefile whenever a command exists there:

```bash
make install
make run
make test
make lint
make format
make typecheck
make migrate
```

Anything not covered by the Makefile must run through `uv run`.

Never invoke a bare `python`, `pytest`, or `django-admin`.

Before reporting work as complete, run:

```bash
make lint
make typecheck
make test
```

Read the actual output. Never claim a check passed without running it.

---

## Source of truth

When information conflicts, use this order:

1. Explicit requirements in the current task
2. Existing source code and tests
3. Repository architecture/convention documentation
4. Established patterns elsewhere in the repository
5. Django/library conventions
6. General best practices

Do not replace an established repository pattern simply because another approach
is newer, more fashionable, or more idiomatic elsewhere.

If documentation contradicts source code:

1. Treat the documentation as authoritative.
2. Correct the stale code when appropriate.
3. Mention the discrepancy in the final report.

Never invent project conventions when the repository already contains an example
that answers the question.

---

## Codebase context

Durable repository knowledge lives here:

```text
docs/
├── architecture.md
├── convention.md
├── handover.md
├── decisions/
├── features/
└── integrations/
```

Before a non-trivial change:

1. Read `docs/architecture.md` when the change touches architecture or multiple apps.
2. Read `docs/convention.md` when changing shared conventions.
3. Read `docs/decisions/` when introducing or changing an architectural pattern.
4. Read `docs/features/index.md`.
5. Read the feature document(s) relevant to the change.
6. Read `docs/integrations/` when the change calls an external system's API.
7. Search the repository for an existing implementation of the same pattern.

Do not rediscover or redesign something that the repository already documents or
implements.

---

## Architecture

Typical structure:

```text
config/
    settings/
        base.py
        local.py
        test.py
        production.py

apps/
    core/
        models
        pagination
        permissions
        exception handling
        health

    catalog/
    orders/
    payments/
        models
        serializers
        views
        urls
        services
        selectors
        permissions
        filters
        admin
        tests
```

The five apps above are the complete set for Phase 1. `catalog` owns categories,
products, variants, and images; `orders` owns orders and their items; `payments`
owns payment records and the gateway client. Do not add a sixth app without an ADR.

`admin.py` is a first-class module here, not an afterthought: in Phase 1 the Django
admin is the merchant's entire back-office. See `docs/decisions/` for the rule on
admin writes and the service layer.

### Layer boundaries

**Views**

- Parse HTTP input.
- Perform request-specific concerns.
- Call a service or selector.
- Return the API response.
- Do not contain business rules.

If a view contains an `if` that determines business state or business policy,
that logic probably belongs elsewhere.

**Services**

- Own domain writes and multi-step business operations.
- Accept plain Python arguments.
- Must not receive request objects or serializers.
- Coordinate transactions when multiple related writes must succeed or fail
  together.

**Selectors**

- Own reusable reads and query construction.
- Own query optimization such as `select_related()` and `prefetch_related()`.
- Do not contain business workflows.

**Serializers**

- Validate API input.
- Serialize output.
- Represent API shape.
- Do not contain reusable business rules or unnecessary database queries.

**Models**

- Own simple domain invariants.
- Declare database constraints and indexes.
- Do not move database integrity rules into application code when PostgreSQL
  can enforce them.

Do not create additional architectural layers such as repositories, unit-of-work
objects, domain objects, or interfaces unless the existing architecture requires
them.

Do not create services or selectors merely to satisfy a naming convention when
the operation is trivial.

---

## Django conventions

- Follow established Django patterns before introducing custom infrastructure.
- Prefer explicit service calls over hidden business behavior through signals.
- Do not use signals for core business workflows unless there is a documented
  architectural reason.
- Prefer Django ORM operations when they clearly express the query.
- Do not use raw SQL merely because it appears more advanced.
- Do not duplicate query logic across models, managers, selectors, and services.
- Keep HTTP concerns out of services and models.
- Keep API representation concerns out of models.
- Keep business workflows out of serializers and views.

---

## Database and transactions

Prefer database-enforced integrity where appropriate:

- `UniqueConstraint`
- `CheckConstraint`
- foreign keys
- indexes

Before adding a query, inspect existing query patterns and indexes.

Do not:

- fetch data merely to perform validation the database can enforce
- add `select_related()` or `prefetch_related()` speculatively
- introduce caching to hide an inefficient query
- add indexes without a query/use-case reason
- use raw SQL when the ORM expresses the operation clearly

Services performing multiple related writes must consider transaction boundaries.

Use `transaction.atomic()` when several database changes must succeed or fail
together.

Do not wrap every service in `atomic()` by default.

Keep external side effects outside database transactions unless there is a
deliberate reason otherwise.

### Migrations

- One migration per logical database change.
- Review generated migrations before applying them.
- Never edit an applied migration.
- Never change `AUTH_USER_MODEL` after the initial migration exists.
- Never put application behavior into migrations unless the migration explicitly
  requires a data migration.
- Verify destructive or potentially expensive migrations carefully.

---

## API compatibility

Treat existing API contracts as stable unless the task explicitly changes them.

Before changing any of these, inspect existing tests and consumers:

- URL structure
- HTTP methods
- response shape
- serializer fields
- status codes
- validation behavior
- error envelope
- pagination format

Do not rename or remove an API field merely to make the implementation cleaner.

---

## Scope discipline

Implement the smallest change that completely satisfies the requirement.

Do not:

- refactor unrelated code
- reformat unrelated files
- rename unrelated variables
- reorganize modules opportunistically
- upgrade dependencies unless required
- "clean up" nearby code without a task-related reason
- rewrite a working subsystem
- add configuration for hypothetical future requirements

If an adjacent problem is discovered, mention it rather than fixing it unless
the fix is necessary for correctness.

---

## Anti-AI-slop rules

Write code as if another experienced engineer will maintain it for years.

Optimize for clarity and correctness, not for the amount of code produced.

Never add code merely to appear comprehensive.

Do not introduce:

- abstractions with one real use
- interfaces or protocols with one implementation
- generic utility functions without a clear owner
- wrapper functions that only rename another function
- speculative extension points
- unnecessary factories or builders
- configuration nobody requested
- defensive checks for impossible states
- redundant validation
- duplicate transformation layers
- unnecessary logging
- broad exception handling
- caching without a demonstrated need
- events or background jobs without a requirement
- compatibility code for versions the project does not support

Prefer:

- existing repository patterns
- direct code over indirection
- explicit dependencies
- small functions with clear responsibilities
- framework conventions
- database constraints
- simple implementations

Do not optimize for hypothetical future requirements.

---

## Requirements discipline

Implement the requirements that exist, not requirements that might exist later.

Do not invent:

- API fields
- business rules
- permissions
- events
- background jobs
- caching
- audit systems
- retries
- abstractions
- configuration
- notification systems

If unspecified behavior materially affects correctness, API behavior, security,
or architecture, ask before implementing it.

If the ambiguity is local and the repository already has an obvious convention,
follow that convention and state the assumption.

---

## Existing changes

Before editing:

```bash
git status
git diff
```

Treat existing uncommitted changes as intentional.

Never:

- reset user changes
- revert user changes
- overwrite unrelated edits
- run destructive git commands
- discard changes because they appear unfinished

If a file already contains user changes, preserve them and modify only what the
current task requires.

---

## Comments and docstrings

Default to **no comment**.

Code should be made clear through naming, structure, and decomposition.

Never write comments that merely narrate code:

```python
# Get the user
user = ...

# Loop through users
for user in users:

# Initialize serializer
serializer = ...

# Return the response
return response
```

Never add:

- commented-out code
- banner comments
- numbered walkthrough comments
- TODO/FIXME comments for work that should be tracked elsewhere
- docstrings that merely repeat a class/function name or signature

Comments are appropriate when they explain information the code cannot express,
especially:

- non-obvious constraints
- external system behavior
- concurrency considerations
- security reasons
- historical compatibility requirements
- surprising framework/database behavior

Comments explain **why**, not **what**.

If a comment is required because a block is difficult to understand, first ask
whether the code can be simplified instead.

---

## Feature documentation

Non-trivial features and cross-cutting changes require a document at:

```text
docs/features/<slug>.md
```

Do not create feature documentation for:

- formatting-only changes
- typo fixes
- trivial mechanical changes
- dependency lockfile changes with no behavioral impact

When in doubt, create the document.

Every feature document must accurately represent the current implementation. Upon every implementation the respective feature documentation must be updated.

### Workflow

1. Read `docs/features/index.md`.
2. Read relevant existing feature documents.
3. Study `docs/features/<slug>.md` before implementation.
4. Fill in the planned scope.
5. Implement the feature.
6. Move completed items from `Remaining` to `Implemented`.
7. Record important architectural decisions.
8. Record surprising behavior or future-agent gotchas.
9. Record relevant tests.
10. Update `docs/features/index.md`.
11. Commit documentation changes with the implementation.

Never claim something is implemented when it is not.

If work is blocked or intentionally incomplete, record it under `Remaining` with
the reason.

---

## Architectural decisions

Architectural decisions belong in:

```text
docs/decisions/
```

Before introducing a new architectural pattern, check existing decisions.

If the repository already has an established decision for the problem, follow it
unless the current task explicitly changes that decision.

If a feature intentionally reverses an existing decision:

1. Document the new decision.
2. Explain why the previous decision no longer applies.
3. Mark the previous decision as superseded when appropriate.

Do not create an ADR for trivial implementation choices.

---

## Tests

Tests are part of the implementation, not a follow-up.

Tests must reflect the behavior being changed.

For API behavior, normally test:

- successful behavior
- relevant authentication/permission boundaries
- validation and important error behavior

For business logic, test:

- normal behavior
- important business-rule boundaries
- meaningful failure/edge cases

For infrastructure/configuration changes, test the observable behavior appropriate
to the change.

Do not add meaningless tests merely to satisfy a checklist.

Before implementing an endpoint or behavior, inspect nearby tests and follow the
repository's established:

- factories/fixtures
- authentication setup
- API client usage
- assertion style
- error assertions

---

## Security

- Secrets come from environment/configuration.
- Never commit credentials or secrets.
- Never add a default production `SECRET_KEY`.
- Do not log passwords, tokens, credentials, or sensitive authentication data.
- Validate authorization at the appropriate boundary.
- Do not assume authentication implies authorization.
- Consider anonymous users and authenticated users accessing another user's data.
- Do not expose fields merely because they exist on the model.
- Treat file uploads, redirects, URLs, and user-controlled HTML carefully.

---

## Skills

Use the repository's available skills when applicable:

| Situation                                                     | Skill              |
| ------------------------------------------------------------- | ------------------ |
| Packaging, typing, module layout, lint configuration          | `python-patterns`  |
| Django settings, models, migrations, ORM, admin               | `django-patterns`  |
| Endpoint design, services/selectors, auth, errors, pagination | `backend-patterns` |
| Final implementation review                                   | `code-reviewer`    |

Repository-specific rules in this file take precedence over generic skill advice
unless following the skill is necessary for correctness or safety.

If a skill materially changes an established repository convention, explain the
conflict before proceeding.

---

## Implementation workflow

For a non-trivial change:

1. Inspect `git status` and existing diffs.
2. Read relevant architecture, convention, decision, and feature documentation.
3. Inspect existing implementations of the same or similar behavior.
4. Identify the smallest design that fits the existing architecture.
5. Create/update the feature document.
6. Implement the change.
7. Add or update tests.
8. Review migrations if applicable.
9. Run formatting/lint/typecheck/tests.
10. Review the complete diff.
11. Run `code-reviewer`.
12. Fix valid findings.
13. Re-run affected checks.
14. Update feature/context documentation.
15. Report the final state.

Do not report completion before the implementation and documentation agree.

---

## Review

Before reporting completion, review the diff as if reviewing another engineer's PR.

Check:

- Does the implementation satisfy the actual requirement?
- Did it introduce unnecessary abstractions?
- Did it modify unrelated code?
- Does it follow existing repository patterns?
- Are service/selector/view/serializer boundaries correct?
- Are permissions correct?
- Are authentication boundaries correct?
- Are error responses consistent?
- Are there N+1 queries?
- Are `select_related()` / `prefetch_related()` appropriate?
- Are database constraints and indexes correct?
- Is the migration safe?
- Are transactions appropriate?
- Are API contracts preserved?
- Are tests meaningful?
- Are comments necessary?
- Are docstrings necessary?
- Is there dead code?
- Are there TODO/FIXME comments?
- Is the feature documentation accurate?

Run `code-reviewer` after the implementation.

Fix every valid finding.

If a finding is intentionally not fixed, record the reason in the final report
rather than silently ignoring it.

---

## Session handoff

At the end of non-trivial work, report only durable information:

### Changed

What behavior/files changed.

### Verified

Commands actually run and their pass/fail results.

### Context learned

Only durable facts that future work should know.

### Remaining

Incomplete work, blockers, or explicitly deferred work.

### Documentation

Which feature, architecture, convention, or decision documents were updated.

Do not provide a transcript of the implementation process.

Do not claim a command passed unless it was actually run.

---

## Definition of done

A non-trivial change is complete only when applicable items are satisfied:

- [ ] Requirement implemented
- [ ] Existing repository patterns followed
- [ ] No unrelated changes
- [ ] Tests added/updated appropriately
- [ ] Migrations reviewed if applicable
- [ ] Lint passes
- [ ] Typecheck passes
- [ ] Tests pass
- [ ] `code-reviewer` run
- [ ] Valid review findings fixed
- [ ] Feature documentation accurate
- [ ] `docs/features/index.md` updated
- [ ] Architectural decisions documented if applicable
- [ ] No commented-out code
- [ ] No unnecessary comments/docstrings
- [ ] No TODO/FIXME left for the completed work
- [ ] Final report accurately states verified and remaining work
