from django.db.models import Count, Exists, OuterRef, Prefetch, Q, QuerySet

from apps.catalog.models import Brand, Category, Product, ProductVariant, Shade, Size

VISIBLE_PRODUCT = Q(is_published=True, brand__is_active=True)

# Annotated rather than prefetched: the card needs one boolean, and prefetching
# every variant to derive it would pull the whole stock table across the network
# to Supabase. It also keeps the filter free of a join and its `.distinct()`.
_HAS_STOCK = Exists(ProductVariant.objects.filter(product=OuterRef("pk"), stock_quantity__gt=0))


def _visible_products() -> QuerySet[Product]:
    return Product.objects.filter(VISIBLE_PRODUCT)


def list_published_products() -> QuerySet[Product]:
    return (
        _visible_products()
        .annotate(in_stock=_HAS_STOCK)
        .select_related("brand", "category")
        .prefetch_related("images")
        # `pk` breaks ties Meta.ordering leaves, so pagination is deterministic.
        .order_by("sort_order", "-created_at", "pk")
    )


def get_published_product_by_slug(*, slug: str) -> Product:
    ordered_variants = Prefetch(
        "variants",
        queryset=ProductVariant.objects.select_related("size", "shade").order_by(
            "size__sort_order",
            "size__name",
            "shade__sort_order",
            "shade__name",
        ),
    )

    return (
        _visible_products()
        .annotate(in_stock=_HAS_STOCK)
        .select_related("brand", "category")
        .prefetch_related(ordered_variants, "images")
        .get(slug=slug)
    )


def list_category_tree() -> QuerySet[Category]:
    return Category.objects.filter(parent__isnull=True).prefetch_related("children")


def _active_brands() -> QuerySet[Brand]:
    return Brand.objects.filter(is_active=True).annotate(
        product_count=Count("products", filter=Q(products__is_published=True))
    )


def list_active_brands() -> QuerySet[Brand]:
    return _active_brands().order_by("sort_order", "name")


def get_active_brand_by_slug(*, slug: str) -> Brand:
    return _active_brands().get(slug=slug)


def _in_use_by_visible_product(lookup: str) -> Exists:
    return Exists(
        ProductVariant.objects.filter(
            **{lookup: OuterRef("pk")},
            product__is_published=True,
            product__brand__is_active=True,
        )
    )


def list_shades_in_use() -> QuerySet[Shade]:
    return Shade.objects.filter(_in_use_by_visible_product("shade")).order_by("sort_order", "name")


def list_sizes_in_use() -> QuerySet[Size]:
    return Size.objects.filter(_in_use_by_visible_product("size")).order_by("sort_order", "name")
