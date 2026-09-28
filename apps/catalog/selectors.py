from django.db.models import Count, Exists, F, OuterRef, Prefetch, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce

from apps.catalog.models import Brand, Category, Product, ProductVariant, Shade, Size, SkinType

VISIBLE_PRODUCT = Q(is_published=True, brand__is_active=True)

# Annotated rather than prefetched: the card needs one boolean, and prefetching
# every variant to derive it would pull the whole stock table across the network
# to Supabase. It also keeps the filter free of a join and its `.distinct()`.
_HAS_STOCK = Exists(ProductVariant.objects.filter(product=OuterRef("pk"), stock_quantity__gt=0))


def _on_sale_variants() -> QuerySet[ProductVariant]:
    """The outer product's variants whose compare-at is above their resolved price,
    the SQL twin of ProductVariant.on_sale."""
    return (
        ProductVariant.objects.filter(product=OuterRef("pk"))
        .annotate(resolved_price=Coalesce("price_override", OuterRef("base_price")))
        .filter(compare_at_price__gt=F("resolved_price"))
    )


PRODUCT_ON_SALE = Exists(_on_sale_variants())


def _with_sale_variant(products: QuerySet[Product]) -> QuerySet[Product]:
    """Annotates the sale variant's price and compare-at: the cheapest on-sale variant,
    ties going to the smaller size. Both are None when nothing is on sale."""
    sale_variant = _on_sale_variants().order_by("resolved_price", "size__sort_order", "pk")[:1]
    return products.annotate(
        sale_price=Subquery(sale_variant.values("resolved_price")),
        sale_compare_at_price=Subquery(sale_variant.values("compare_at_price")),
    )


def _visible_products() -> QuerySet[Product]:
    return Product.objects.filter(VISIBLE_PRODUCT)


def list_published_products() -> QuerySet[Product]:
    return (
        _with_sale_variant(_visible_products())
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
        _with_sale_variant(_visible_products())
        .annotate(in_stock=_HAS_STOCK)
        .select_related("brand", "category")
        .prefetch_related(ordered_variants, "images", "skin_types")
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


def list_skin_types_in_use() -> QuerySet[SkinType]:
    return SkinType.objects.filter(
        Exists(
            Product.skin_types.through.objects.filter(
                skintype=OuterRef("pk"),
                product__is_published=True,
                product__brand__is_active=True,
            )
        )
    ).order_by("sort_order", "name")
