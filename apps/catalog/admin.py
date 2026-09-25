from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.db import IntegrityError, transaction
from django.db.models import QuerySet, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.catalog.models import Category, Color, Product, ProductImage, ProductVariant, Size
from apps.catalog.services import set_variant_stock

# `sku` is generated, never typed, so the scheme is a convention the merchant reads
# on packing lists and searches by. Built from the product slug and the two lookup
# slugs, which makes it unique whenever the slug fits: the product slug is unique
# and (product, size, color) is unique.
#
# It is *not* unique when the slug has to be truncated to fit the column -- two
# products agreeing in their first forty-odd characters produce the same SKU. That
# is rare and the merchant can fix it by shortening a slug, so the action reports
# the clash rather than inventing an opaque suffix to avoid it.
SKU_MAX_LENGTH = 64


def generate_sku(*, product: Product, size: Size, color: Color) -> str:
    suffix = f"-{size.slug}-{color.slug}".upper()
    stem = product.slug.upper()[: SKU_MAX_LENGTH - len(suffix)]
    return f"{stem}{suffix}"


class ProductVariantInline(admin.TabularInline):  # type: ignore[type-arg]  # not subscriptable at runtime
    model = ProductVariant
    extra = 0
    # Stock is not editable here. An inline formset writes rows directly, and an
    # absolute write with no lock discards a concurrent checkout's decrement. The
    # "Adjust stock" action on ProductVariantAdmin is the locked path.
    readonly_fields = ("stock_quantity",)
    fields = ("size", "color", "sku", "price_override", "stock_quantity")


class ProductImageInline(admin.TabularInline):  # type: ignore[type-arg]  # not subscriptable at runtime
    model = ProductImage
    extra = 0
    fields = ("image", "alt_text", "sort_order", "is_primary")


@admin.register(Size)
class SizeAdmin(admin.ModelAdmin):  # type: ignore[type-arg]  # not subscriptable at runtime
    # Plain catalogue editing, so ADR 0002 permits the naive ModelAdmin. This and
    # ColorAdmin are what unblock the catalogue at all: both tables ship empty and
    # a variant cannot be created until they hold rows.
    list_display = ("name", "slug", "sort_order")
    list_editable = ("sort_order",)
    ordering = ("sort_order", "name")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):  # type: ignore[type-arg]  # not subscriptable at runtime
    list_display = ("name", "slug", "sort_order")
    list_editable = ("sort_order",)
    ordering = ("sort_order", "name")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):  # type: ignore[type-arg]  # not subscriptable at runtime
    list_display = ("name", "slug", "parent", "sort_order")
    list_editable = ("sort_order",)
    list_filter = ("parent",)
    ordering = ("sort_order", "name")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


class GenerateVariantsForm(forms.Form):
    sizes = forms.ModelMultipleChoiceField(
        queryset=Size.objects.all(), widget=forms.CheckboxSelectMultiple
    )
    colors = forms.ModelMultipleChoiceField(
        queryset=Color.objects.all(), widget=forms.CheckboxSelectMultiple
    )


class AdjustStockForm(forms.Form):
    quantity = forms.IntegerField(min_value=0, help_text="The counted total, not a change.")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):  # type: ignore[type-arg]  # not subscriptable at runtime
    inlines = (ProductVariantInline, ProductImageInline)
    list_display = ("name", "category", "base_price", "is_published", "total_stock")
    list_filter = ("is_published", "category")
    ordering = ("sort_order", "-created_at")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")
    actions = ("generate_variants",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[Product]:
        # Annotated rather than summed per row: the changelist renders every product
        # on the page, and a property would be one query each.
        products: QuerySet[Product] = super().get_queryset(request)
        return products.select_related("category").annotate(
            total_stock=Sum("variants__stock_quantity")
        )

    @admin.display(description="Stock", ordering="total_stock")
    def total_stock(self, product: Product) -> int:
        return getattr(product, "total_stock", None) or 0

    @admin.action(description="Generate variants for the selected products")
    def generate_variants(
        self, request: HttpRequest, queryset: QuerySet[Product]
    ) -> HttpResponse | None:
        """Creates the missing size-and-colour combinations, skipping what exists.

        A garment in five sizes and three colours is fifteen rows with a unique SKU
        on each, which is fifteen chances to mistype one.
        """
        form = GenerateVariantsForm(request.POST if "apply" in request.POST else None)

        if not form.is_valid():
            return render(
                request,
                "admin/catalog/generate_variants.html",
                {
                    "form": form,
                    "products": queryset,
                    "action_checkbox_name": ACTION_CHECKBOX_NAME,
                    "selected": request.POST.getlist(ACTION_CHECKBOX_NAME),
                },
            )

        sizes = form.cleaned_data["sizes"]
        colors = form.cleaned_data["colors"]
        created = 0
        skipped = 0

        clashed: list[str] = []

        for product in queryset.prefetch_related("variants"):
            existing = {(variant.size_id, variant.color_id) for variant in product.variants.all()}
            missing = [
                ProductVariant(
                    product=product,
                    size=size,
                    color=color,
                    sku=generate_sku(product=product, size=size, color=color),
                )
                for size in sizes
                for color in colors
                if (size.pk, color.pk) not in existing
            ]
            skipped += len(sizes) * len(colors) - len(missing)

            try:
                # Its own savepoint, not merely its own try: Django's changelist
                # wraps the whole action in a transaction, so an IntegrityError
                # caught without one leaves the connection unusable and every
                # following query -- including the session read that renders the
                # result page -- fails with TransactionManagementError.
                with transaction.atomic():
                    ProductVariant.objects.bulk_create(missing)
            except IntegrityError:
                # A truncated slug collided with another product's. Reported per
                # product rather than raised, so the rest of the selection still
                # gets its variants.
                clashed.append(product.slug)
            else:
                created += len(missing)

        self.message_user(
            request,
            f"Created {created} variants. {skipped} already existed.",
            messages.SUCCESS if created else messages.WARNING,
        )
        if clashed:
            self.message_user(
                request,
                "Could not generate for "
                f"{', '.join(clashed)}: the generated SKU is already taken. "
                "Shorten the product slug and try again.",
                messages.ERROR,
            )
        return None


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):  # type: ignore[type-arg]  # not subscriptable at runtime
    list_display = ("sku", "product", "size", "color", "stock_quantity", "price_override")
    list_filter = ("size", "color", "product__is_published")
    ordering = ("product__name", "size__sort_order")
    search_fields = ("sku", "product__name")
    # Readonly here too, not only in the inline: the change form writes the same
    # column just as unlocked.
    readonly_fields = ("stock_quantity",)
    actions = ("adjust_stock",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[ProductVariant]:
        variants: QuerySet[ProductVariant] = super().get_queryset(request)
        return variants.select_related("product", "size", "color")

    @admin.action(description="Adjust stock for the selected variants")
    def adjust_stock(
        self, request: HttpRequest, queryset: QuerySet[ProductVariant]
    ) -> HttpResponse | None:
        """Sets an absolute count through the service, which takes the row lock."""
        form = AdjustStockForm(request.POST if "apply" in request.POST else None)

        if not form.is_valid():
            return render(
                request,
                "admin/catalog/adjust_stock.html",
                {
                    "form": form,
                    "variants": queryset,
                    "action_checkbox_name": ACTION_CHECKBOX_NAME,
                    "selected": request.POST.getlist(ACTION_CHECKBOX_NAME),
                },
            )

        quantity = form.cleaned_data["quantity"]
        for variant in queryset:
            set_variant_stock(variant=variant, quantity=quantity)

        self.message_user(
            request, f"Set stock to {quantity} on {queryset.count()} variants.", messages.SUCCESS
        )
        return None


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):  # type: ignore[type-arg]  # not subscriptable at runtime
    list_display = ("product", "alt_text", "sort_order", "is_primary")
    list_filter = ("is_primary",)
    ordering = ("product__name", "sort_order")
    search_fields = ("product__name", "alt_text")

    def get_queryset(self, request: HttpRequest) -> QuerySet[ProductImage]:
        images: QuerySet[ProductImage] = super().get_queryset(request)
        return images.select_related("product")
