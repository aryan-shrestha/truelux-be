from django.db.models import Model
from django.utils.text import slugify


def unique_slug(*, model: type[Model], name: str, max_length: int) -> str:
    """Derives a slug from `name`, suffixed -2, -3... until no row of `model` has it.

    A concurrent writer can still take the same slug between this read and the
    insert; the unique constraint then raises IntegrityError, a 409.
    """
    base = slugify(name)[:max_length] or "item"
    candidate = base
    suffix = 2
    while model._default_manager.filter(slug=candidate).exists():
        tail = f"-{suffix}"
        candidate = f"{base[: max_length - len(tail)]}{tail}"
        suffix += 1
    return candidate
