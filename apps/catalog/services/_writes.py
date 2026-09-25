from collections.abc import Mapping
from typing import Any

from django.db.models import Model
from django.utils.text import slugify


def assign_fields(instance: Model, fields: Mapping[str, Any], allowed: frozenset[str]) -> None:
    """Raises ValueError for a field outside `allowed`, so a caller cannot slip a
    rule-bearing field such as `is_published` past the service that guards it."""
    for name, value in fields.items():
        if name not in allowed:
            raise ValueError(f"{type(instance).__name__}.{name} is not writable here.")
        setattr(instance, name, value)


def fill_missing_slug(instance: Any) -> None:
    """Derives a slug from the name, suffixed -2, -3... until no row has it.

    A concurrent writer can still take the same slug between this read and the
    insert; the unique constraint then raises IntegrityError, a 409.
    """
    if instance.slug:
        return
    model = type(instance)
    max_length = model._meta.get_field("slug").max_length
    base = slugify(instance.name)[:max_length] or "item"
    candidate = base
    suffix = 2
    while model._default_manager.filter(slug=candidate).exists():
        tail = f"-{suffix}"
        candidate = f"{base[: max_length - len(tail)]}{tail}"
        suffix += 1
    instance.slug = candidate
