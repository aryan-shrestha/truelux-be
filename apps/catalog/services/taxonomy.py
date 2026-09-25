from collections.abc import Mapping
from typing import Any

from django.core.exceptions import ValidationError

from apps.catalog.models import Brand, Category, Shade, Size
from apps.catalog.services._slugs import unique_slug
from apps.core.logging import get_logger

logger = get_logger(__name__)

WRITABLE_FIELDS: dict[type[Brand | Category | Shade | Size], frozenset[str]] = {
    Brand: frozenset({"name", "slug", "description", "logo", "is_active", "sort_order"}),
    Category: frozenset({"name", "slug", "parent", "sort_order"}),
    Shade: frozenset({"name", "slug", "hex_code", "sort_order"}),
    Size: frozenset({"name", "slug", "sort_order"}),
}


def _save[E: (Brand, Category, Shade, Size)](entry: E, fields: Mapping[str, Any]) -> E:
    allowed = WRITABLE_FIELDS[type(entry)]
    for name, value in fields.items():
        if name not in allowed:
            raise ValueError(f"{type(entry).__name__}.{name} is not writable here.")
        setattr(entry, name, value)
    if not entry.slug:
        max_length = type(entry)._meta.get_field("slug").max_length or 50
        entry.slug = unique_slug(model=type(entry), name=entry.name, max_length=max_length)
    entry.save()
    return entry


def create_taxonomy_entry[E: (Brand, Category, Shade, Size)](
    *, model: type[E], fields: Mapping[str, Any]
) -> E:
    entry = _save(model(), fields)
    logger.info("catalog.taxonomy_created", model=model.__name__, entry_id=str(entry.pk))
    return entry


def update_taxonomy_entry[E: (Brand, Category, Shade, Size)](
    *, entry: E, fields: Mapping[str, Any]
) -> E:
    """Raises ValidationError (a 400) when a category would become its own ancestor."""
    if isinstance(entry, Category) and fields.get("parent") is not None:
        _reject_category_cycle(category=entry, parent=fields["parent"])
    _save(entry, fields)
    logger.info("catalog.taxonomy_updated", model=type(entry).__name__, entry_id=str(entry.pk))
    return entry


def delete_taxonomy_entry(*, entry: Brand | Category | Shade | Size) -> None:
    """Raises ProtectedError (a 409) while any product or variant refers to it."""
    entry_id = str(entry.pk)
    entry.delete()
    logger.info("catalog.taxonomy_deleted", model=type(entry).__name__, entry_id=entry_id)


def _reject_category_cycle(*, category: Category, parent: Category) -> None:
    ancestor: Category | None = parent
    while ancestor is not None:
        if ancestor.pk == category.pk:
            raise ValidationError({"parent_id": "A category cannot be its own ancestor."})
        ancestor = ancestor.parent
