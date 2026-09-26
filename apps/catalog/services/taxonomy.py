from collections.abc import Mapping
from typing import Any

from django.core.exceptions import ValidationError

from apps.catalog.models import Brand, Category, Shade, Size, SkinType
from apps.catalog.services._writes import assign_fields, fill_missing_slug
from apps.core.logging import get_logger

logger = get_logger(__name__)

WRITABLE_FIELDS: dict[type[Brand | Category | Shade | Size | SkinType], frozenset[str]] = {
    Brand: frozenset({"name", "slug", "description", "logo", "is_active", "sort_order"}),
    Category: frozenset({"name", "slug", "parent", "sort_order"}),
    Shade: frozenset({"name", "slug", "hex_code", "sort_order"}),
    Size: frozenset({"name", "slug", "sort_order"}),
    SkinType: frozenset({"name", "slug", "sort_order"}),
}


def _save[E: (Brand, Category, Shade, Size, SkinType)](entry: E, fields: Mapping[str, Any]) -> E:
    assign_fields(entry, fields, WRITABLE_FIELDS[type(entry)])
    fill_missing_slug(entry)
    entry.save()
    return entry


def create_taxonomy_entry[E: (Brand, Category, Shade, Size, SkinType)](
    *, model: type[E], fields: Mapping[str, Any]
) -> E:
    entry = _save(model(), fields)
    logger.info("catalog.taxonomy_created", model=model.__name__, entry_id=str(entry.pk))
    return entry


def update_taxonomy_entry[E: (Brand, Category, Shade, Size, SkinType)](
    *, entry: E, fields: Mapping[str, Any]
) -> E:
    """Raises ValidationError (a 400) when a category would become its own ancestor."""
    if isinstance(entry, Category) and fields.get("parent") is not None:
        _reject_category_cycle(category=entry, parent=fields["parent"])
    _save(entry, fields)
    logger.info("catalog.taxonomy_updated", model=type(entry).__name__, entry_id=str(entry.pk))
    return entry


def delete_taxonomy_entry(*, entry: Brand | Category | Shade | Size | SkinType) -> None:
    """Raises ProtectedError (a 409) while any product or variant refers to it.
    A skin type is never protected: deleting it detaches it from its products."""
    entry_id = str(entry.pk)
    entry.delete()
    logger.info("catalog.taxonomy_deleted", model=type(entry).__name__, entry_id=entry_id)


def _reject_category_cycle(*, category: Category, parent: Category) -> None:
    ancestor: Category | None = parent
    while ancestor is not None:
        if ancestor.pk == category.pk:
            raise ValidationError({"parent_id": "A category cannot be its own ancestor."})
        ancestor = ancestor.parent
