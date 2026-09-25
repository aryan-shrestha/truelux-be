# <Feature name>

Status: Planned

Last updated: YYYY-MM-DD

---

## Goal

What problem does this feature solve?

Keep this short.

---

## Scope

What is included in this implementation?

- ...
- ...
- ...

What is explicitly outside the scope?

- ...
- ...

---

## Context

What existing code or architecture is relevant?

Mention the important models, services, selectors, permissions, APIs, or external
systems that future implementation work needs to understand.

---

## Planned

The intended implementation:

- ...
- ...
- ...

---

## Implemented

Only record behavior that actually exists in the code.

- `apps/<domain>/models.py` — ...
- `apps/<domain>/services.py` — ...
- `apps/<domain>/selectors.py` — ...
- `apps/<domain>/views.py` — ...
- `apps/<domain>/tests/...` — ...

---

## Remaining

Anything incomplete, intentionally deferred, or blocked.

If nothing remains:

```text
None.
```

If blocked, explain why:

```text
- Add X after Y is available because ...
```

Do not hide incomplete work.

---

## Decisions

Record decisions that future implementation work needs to preserve.

### Decision: <short title>

**Decision**

...

**Reason**

...

**Consequence**

...

---

## Gotchas

Record surprising behavior, constraints, or implementation details that are easy
for a future engineer or AI agent to miss.

Examples:

- Authentication is enforced by `<location>`, not individual views.
- The database constraint is case-insensitive.
- This endpoint must not use the cached selector because ...
- The external API sends duplicate webhooks.

Only record durable knowledge.

---

## API

Document API behavior when relevant.

### Endpoint

```text
METHOD /api/...
```

### Request

```json
{}
```

### Response

```json
{}
```

### Errors

```json
{}
```

Do not duplicate the entire API documentation if another authoritative document
already exists.

---

## Data changes

Document relevant:

- models
- fields
- constraints
- indexes
- migrations
- data migrations

If there are no data changes:

```text
None.
```

---

## Permissions

Document important authorization rules.

Examples:

- authenticated users only
- users can only access their own records
- administrators can access all records

---

## Tests

Record the tests that verify the feature.

- `apps/<domain>/tests/test_....py::test_...`
- `apps/<domain>/tests/test_....py::test_...`

Include important scenarios rather than every test name.

---

## Files

List the important files involved in the feature.

```text
apps/<domain>/
├── models.py
├── serializers.py
├── services.py
├── selectors.py
├── views.py
└── tests/
```

---

## Future context

Only record information that will save a future session from rediscovering
something important.

Do not write a chronological implementation diary.
