from django.db.models import Exists, OuterRef, Prefetch, QuerySet

from apps.catalog.models import Category, Product, ProductVariant

# Annotated rather than prefetched: the card needs one boolean, and prefetching
# every variant to derive it would pull the whole stock table across the network
# to Supabase. It also keeps the filter free of a join and its `.distinct()`.
_HAS_STOCK = Exists(ProductVariant.objects.filter(product=OuterRef("pk"), stock_quantity__gt=0))


def list_published_products() -> QuerySet[Product]:
    return (
        Product.objects.filter(is_published=True)
        .annotate(in_stock=_HAS_STOCK)
        .select_related("category")
        .prefetch_related("images")
        # `pk` is the tiebreaker Meta.ordering lacks: two products sharing a
        # sort_order and a created_at would otherwise paginate inconsistently.
        .order_by("sort_order", "-created_at", "pk")
    )


def get_published_product_by_slug(*, slug: str) -> Product:
    ordered_variants = Prefetch(
        "variants",
        # ProductVariant has no Meta.ordering, deliberately, so that ordering by
        # size does not join two lookup tables on every variant read in the
        # system. This is the endpoint that renders variants, so it orders them.
        queryset=ProductVariant.objects.select_related("size", "color").order_by(
            "size__sort_order",
            "size__name",
            "color__sort_order",
            "color__name",
        ),
    )

    return (
        Product.objects.filter(is_published=True)
        .annotate(in_stock=_HAS_STOCK)
        .select_related("category")
        .prefetch_related(ordered_variants, "images")
        .get(slug=slug)
    )


def list_category_tree() -> QuerySet[Category]:
    return Category.objects.filter(parent__isnull=True).prefetch_related("children")
