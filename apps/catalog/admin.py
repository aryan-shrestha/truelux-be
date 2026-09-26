from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.db import IntegrityError, transaction
from django.db.models import QuerySet, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.catalog.models import (
    Brand,
    Category,
    Product,
    ProductImage,
    ProductVariant,
    Shade,
    Size,
    SkinType,
)
from apps.catalog.services import set_variant_stock, update_product, update_product_image
from apps.core.exceptions import DomainError

# Generated from the product, size and shade slugs, so it is unique whenever the
# product slug fits. A truncated slug can collide with another product's; the
# action reports that rather than inventing an opaque suffix.
SKU_MAX_LENGTH = 64


def generate_sku(*, product: Product, size: Size, shade: Shade | None) -> str:
    suffix = f"-{size.slug}" + (f"-{shade.slug}" if shade else "")
    suffix = suffix.upper()
    stem = product.slug.upper()[: SKU_MAX_LENGTH - len(suffix)]
    return f"{stem}{suffix}"


class ProductVariantInline(admin.TabularInline):  # type: ignore[type-arg]  # not subscriptable at runtime
    model = ProductVariant
    extra = 0
    # An inline formset writes stock unlocked and would discard a concurrent
    # checkout's decrement. "Adjust stock" on ProductVariantAdmin is the locked path.
    readonly_fields = ("stock_quantity",)
    fields = ("size", "shade", "sku", "price_override", "stock_quantity")


class ProductImageInline(admin.TabularInline):  # type: ignore[type-arg]  # not subscriptable at runtime
    model = ProductImage
    extra = 0
    fields = ("image", "alt_text", "sort_order", "is_primary")


class LookupAdmin(admin.ModelAdmin):  # type: ignore[type-arg]  # not subscriptable at runtime
    list_display: tuple[str, ...] = ("name", "slug", "sort_order")
    list_editable = ("sort_order",)
    ordering = ("sort_order", "name")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


@admin.register(Brand)
class BrandAdmin(LookupAdmin):
    list_display = ("name", "slug", "is_active", "sort_order")
    list_filter = ("is_active",)


@admin.register(Size)
class SizeAdmin(LookupAdmin):
    pass


@admin.register(Shade)
class ShadeAdmin(LookupAdmin):
    list_display = ("name", "slug", "hex_code", "sort_order")


@admin.register(SkinType)
class SkinTypeAdmin(LookupAdmin):
    pass


@admin.register(Category)
class CategoryAdmin(LookupAdmin):
    list_display = ("name", "slug", "parent", "sort_order")
    list_filter = ("parent",)


class GenerateVariantsForm(forms.Form):
    sizes = forms.ModelMultipleChoiceField(
        queryset=Size.objects.all(), widget=forms.CheckboxSelectMultiple
    )
    shades = forms.ModelMultipleChoiceField(
        queryset=Shade.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Leave empty for a product without shades.",
    )


class AdjustStockForm(forms.Form):
    quantity = forms.IntegerField(min_value=0, help_text="The counted total, not a change.")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):  # type: ignore[type-arg]  # not subscriptable at runtime
    inlines = (ProductVariantInline, ProductImageInline)
    list_display = ("name", "brand", "category", "base_price", "is_published", "total_stock")
    list_filter = ("is_published", "brand", "category", "skin_types")
    filter_horizontal = ("skin_types",)
    ordering = ("sort_order", "-created_at")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")
    # Publishing has a rule (a product needs a variant), so it is an action on the
    # service rather than a form field (ADR 0002).
    readonly_fields = ("is_published",)
    actions = ("generate_variants", "publish", "unpublish")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Product]:
        products: QuerySet[Product] = super().get_queryset(request)
        return products.select_related("brand", "category").annotate(
            total_stock=Sum("variants__stock_quantity")
        )

    @admin.display(description="Stock", ordering="total_stock")
    def total_stock(self, product: Product) -> int:
        return getattr(product, "total_stock", None) or 0

    def _set_published(
        self, request: HttpRequest, products: QuerySet[Product], *, is_published: bool
    ) -> None:
        done: list[str] = []
        failed: list[str] = []
        for product in products:
            try:
                update_product(product=product, fields={}, is_published=is_published)
            except DomainError as exc:
                failed.append(f"{product.name} ({exc.message})")
            else:
                done.append(product.name)

        verb = "Published" if is_published else "Unpublished"
        if done:
            self.message_user(request, f"{verb} {len(done)}: {', '.join(done)}.", messages.SUCCESS)
        if failed:
            self.message_user(request, f"Could not publish {'; '.join(failed)}.", messages.WARNING)

    @admin.action(description="Publish the selected products")
    def publish(self, request: HttpRequest, queryset: QuerySet[Product]) -> None:
        self._set_published(request, queryset, is_published=True)

    @admin.action(description="Unpublish the selected products")
    def unpublish(self, request: HttpRequest, queryset: QuerySet[Product]) -> None:
        self._set_published(request, queryset, is_published=False)

    @admin.action(description="Generate variants for the selected products")
    def generate_variants(
        self, request: HttpRequest, queryset: QuerySet[Product]
    ) -> HttpResponse | None:
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

        sizes = list(form.cleaned_data["sizes"])
        shades: list[Shade | None] = list(form.cleaned_data["shades"]) or [None]
        created = 0
        skipped = 0
        clashed: list[str] = []

        for product in queryset.prefetch_related("variants"):
            existing = {(variant.size_id, variant.shade_id) for variant in product.variants.all()}
            missing = [
                ProductVariant(
                    product=product,
                    size=size,
                    shade=shade,
                    sku=generate_sku(product=product, size=size, shade=shade),
                )
                for size in sizes
                for shade in shades
                if (size.pk, shade.pk if shade else None) not in existing
            ]
            skipped += len(sizes) * len(shades) - len(missing)

            try:
                # A savepoint, not just a try: the changelist wraps the action in a
                # transaction, and an IntegrityError caught without one leaves the
                # connection unusable for the rest of the request.
                with transaction.atomic():
                    ProductVariant.objects.bulk_create(missing)
            except IntegrityError:
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
    list_display = ("sku", "product", "size", "shade", "stock_quantity", "price_override")
    list_filter = ("size", "shade", "product__is_published")
    ordering = ("product__name", "size__sort_order")
    search_fields = ("sku", "product__name")
    readonly_fields = ("stock_quantity",)
    actions = ("adjust_stock",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[ProductVariant]:
        variants: QuerySet[ProductVariant] = super().get_queryset(request)
        return variants.select_related("product", "size", "shade")

    @admin.action(description="Adjust stock for the selected variants")
    def adjust_stock(
        self, request: HttpRequest, queryset: QuerySet[ProductVariant]
    ) -> HttpResponse | None:
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
    # Promotion clears the old primary in one transaction, which a form save cannot do.
    readonly_fields = ("is_primary",)
    actions = ("make_primary",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[ProductImage]:
        images: QuerySet[ProductImage] = super().get_queryset(request)
        return images.select_related("product")

    @admin.action(description="Make the selected image its product's primary")
    def make_primary(self, request: HttpRequest, queryset: QuerySet[ProductImage]) -> None:
        for image in queryset:
            update_product_image(image=image, fields={}, is_primary=True)
        self.message_user(request, f"Promoted {queryset.count()} images.", messages.SUCCESS)
