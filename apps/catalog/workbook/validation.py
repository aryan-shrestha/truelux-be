from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from django.db.models import Count
from django.utils.text import slugify
from PIL import Image, UnidentifiedImageError

from apps.catalog.constants import ALLOWED_IMAGE_FORMATS, MAX_IMAGE_BYTES
from apps.catalog.exceptions import ProductHasNoVariants
from apps.catalog.models import (
    Brand,
    Category,
    Product,
    ProductVariant,
    Shade,
    Size,
    SkinType,
)
from apps.catalog.workbook.layout import (
    BRANDS,
    CATEGORIES,
    PRODUCTS,
    SHADES,
    SIZES,
    SKIN_TYPES,
    VARIANTS,
    Sheet,
)
from apps.catalog.workbook.reader import Problem, Row

type CategoryKey = tuple[str, str | None]
# A product already in the database is known by its primary key; a new one by the
# slug its name will get.
type ProductKey = UUID | str


def split_list(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


class Catalogue:
    """The database's catalogue, read once so validation and the writes agree."""

    def __init__(self) -> None:
        self.brands = {brand.name: brand for brand in Brand.objects.all()}
        self.shades = {shade.name: shade for shade in Shade.objects.all()}
        self.sizes = {size.name: size for size in Size.objects.all()}
        self.skin_types = {skin_type.name: skin_type for skin_type in SkinType.objects.all()}
        self.categories: dict[CategoryKey, Category] = {
            (category.name, category.parent.name if category.parent else None): category
            for category in Category.objects.select_related("parent")
        }
        products = Product.objects.annotate(image_count=Count("images")).prefetch_related(
            "skin_types"
        )
        self.products_by_slug = {product.slug: product for product in products}
        self.products_by_name: dict[str, list[Product]] = defaultdict(list)
        for product in self.products_by_slug.values():
            self.products_by_name[product.name].append(product)
        self.variants = {
            variant.sku: variant
            for variant in ProductVariant.objects.select_related("product", "size", "shade")
        }

    def find_product(self, name: str) -> Product | None:
        """By the slug of its name, or else by its exact name: a product created in the
        admin app may carry a slug of its own."""
        if product := self.products_by_slug.get(slugify(name)):
            return product
        matches = self.products_by_name.get(name, [])
        return matches[0] if len(matches) == 1 else None

    def product_key(self, name: str) -> ProductKey:
        product = self.find_product(name)
        return product.pk if product else slugify(name)


@dataclass
class Plan:
    rows: dict[Sheet, list[Row]]
    problems: list[Problem] = field(default_factory=list)
    # Rows whose image files will be uploaded, with the resolved file paths.
    brand_logos: dict[int, Path] = field(default_factory=dict)
    product_images: dict[int, list[Path]] = field(default_factory=dict)


class Validator:
    def __init__(
        self,
        rows: dict[Sheet, list[Row]],
        catalogue: Catalogue,
        *,
        images_dir: Path | None,
        replace_images: bool,
    ) -> None:
        self.rows = rows
        self.catalogue = catalogue
        self.images_dir = images_dir
        self.replace_images = replace_images
        self.plan = Plan(rows)
        self._image_names = (
            {path.name for path in images_dir.iterdir() if path.is_file()}
            if images_dir and images_dir.is_dir()
            else set()
        )

    def validate(self) -> Plan:
        self._unique_names(BRANDS, "Name")
        self._unique_names(SHADES, "Name")
        self._unique_names(SIZES, "Name")
        self._unique_names(SKIN_TYPES, "Name")
        self._check_brand_logos()
        self._check_categories()
        self._check_products()
        self._check_variants()
        self._check_published_products_have_variants()
        return self.plan

    def _problem(self, row: Row, column: str, message: str) -> None:
        self.plan.problems.append(Problem(row.sheet.title, message, row.number, column))

    def _names_on(self, sheet: Sheet, column: str = "Name") -> set[str]:
        return {row[column] for row in self.rows[sheet] if row[column]}

    def _unique_names(self, sheet: Sheet, column: str) -> None:
        seen: dict[str, int] = {}
        for row in self.rows[sheet]:
            name = row[column]
            if name is None:
                continue
            if name in seen:
                self._problem(row, column, f'"{name}" is already on row {seen[name]}')
            else:
                seen[name] = row.number

    def _check_reference(self, row: Row, column: str, sheet: Sheet, known: set[str]) -> None:
        value = row[column]
        if value is not None and value not in known:
            self._problem(row, column, f'"{value}" is not on the {sheet.title} sheet')

    def _check_brand_logos(self) -> None:
        for row in self.rows[BRANDS]:
            logo = row["Logo file"]
            if not logo:
                continue
            brand = self.catalogue.brands.get(row["Name"])
            if brand is not None and brand.logo and not self.replace_images:
                continue
            if path := self._image_file(row, "Logo file", logo):
                self.plan.brand_logos[row.number] = path

    def _check_categories(self) -> None:
        rows = self.rows[CATEGORIES]
        top_level = {row["Name"] for row in rows if row["Name"] and not row["Parent category"]}
        top_level |= {name for name, parent in self.catalogue.categories if parent is None}
        children = {row["Name"] for row in rows if row["Parent category"]}
        seen: dict[CategoryKey, int] = {}
        for row in rows:
            name, parent = row["Name"], row["Parent category"]
            if name is None:
                continue
            key = (name, parent)
            if key in seen:
                self._problem(row, "Name", f'"{name}" is already on row {seen[key]}')
            seen.setdefault(key, row.number)
            if parent is None:
                continue
            if parent == name:
                self._problem(row, "Parent category", "a category cannot be its own parent")
            elif parent not in top_level:
                message = (
                    f'"{parent}" is itself a sub-category; categories are one level deep only'
                    if parent in children
                    else f'"{parent}" is not on the Categories sheet'
                )
                self._problem(row, "Parent category", message)

    def category_candidates(self, name: str) -> set[CategoryKey]:
        on_sheet = {
            (row["Name"], row["Parent category"])
            for row in self.rows[CATEGORIES]
            if row["Name"] == name
        }
        in_database = {key for key in self.catalogue.categories if key[0] == name}
        return on_sheet | in_database

    def _check_products(self) -> None:
        brands = self._names_on(BRANDS) | set(self.catalogue.brands)
        skin_types = self._names_on(SKIN_TYPES) | set(self.catalogue.skin_types)
        seen: dict[str, int] = {}
        for row in self.rows[PRODUCTS]:
            name = row["Product name"]
            if name is not None:
                slug = slugify(name)
                if not slug:
                    self._problem(row, "Product name", "needs at least one letter or digit")
                elif slug in seen:
                    self._problem(row, "Product name", f'"{name}" is already on row {seen[slug]}')
                else:
                    seen[slug] = row.number
            self._check_reference(row, "Brand", BRANDS, brands)
            self._check_category(row)
            for skin_type in split_list(row["Skin types"]):
                if skin_type not in skin_types:
                    self._problem(
                        row, "Skin types", f'"{skin_type}" is not on the Skin types sheet'
                    )
            self._check_product_images(row)

    def _check_category(self, row: Row) -> None:
        name = row["Category"]
        if name is None:
            return
        candidates = self.category_candidates(name)
        if not candidates:
            self._problem(row, "Category", f'"{name}" is not on the Categories sheet')
        elif len(candidates) > 1:
            parents = ", ".join(sorted(parent or "top level" for _, parent in candidates))
            self._problem(
                row,
                "Category",
                f'"{name}" is ambiguous: there is one under each of {parents}. '
                "Rename one of them on the Categories sheet",
            )

    def _check_product_images(self, row: Row) -> None:
        files = split_list(row["Image files"])
        if not files or row["Product name"] is None:
            return
        product = self.catalogue.find_product(row["Product name"])
        if product is not None and product.image_count and not self.replace_images:  # type: ignore[attr-defined]
            return
        paths = [self._image_file(row, "Image files", name) for name in files]
        self.plan.product_images[row.number] = [path for path in paths if path]

    def _image_file(self, row: Row, column: str, name: str) -> Path | None:
        if Path(name).name != name or name in {".", ".."}:
            self._problem(row, column, f'"{name}" must be a file name, not a path')
            return None
        if self.images_dir is None:
            self._problem(row, column, f'"{name}" needs the images folder: pass --images <folder>')
            return None
        if name not in self._image_names:
            self._problem(row, column, f'"{name}" is not in the images folder')
            return None
        path = self.images_dir / name
        size = path.stat().st_size
        if size > MAX_IMAGE_BYTES:
            self._problem(
                row, column, f'"{name}" is {size / 1024 / 1024:.1f} MB; the limit is 5 MB'
            )
            return None
        try:
            with Image.open(path) as image:
                image_format = image.format
        except UnidentifiedImageError:
            image_format = None
        if image_format not in ALLOWED_IMAGE_FORMATS:
            self._problem(row, column, f'"{name}" is not a JPEG, PNG or WebP image')
            return None
        return path

    def _check_variants(self) -> None:
        sheet_products = {
            slugify(row["Product name"]): row for row in self.rows[PRODUCTS] if row["Product name"]
        }
        sizes = self._names_on(SIZES) | set(self.catalogue.sizes)
        shades = self._names_on(SHADES) | set(self.catalogue.shades)
        skus: dict[str, int] = {}
        combinations: dict[tuple[ProductKey, str, str | None], int] = {}

        for row in self.rows[VARIANTS]:
            sku, product_name = row["SKU"], row["Product name"]
            if sku is not None:
                if sku in skus:
                    self._problem(row, "SKU", f'"{sku}" is already on row {skus[sku]}')
                skus.setdefault(sku, row.number)
            self._check_reference(row, "Size", SIZES, sizes)
            self._check_reference(row, "Shade", SHADES, shades)
            if row["Price override (NPR)"] == 0:
                self._problem(
                    row,
                    "Price override (NPR)",
                    "must be more than 0; leave it blank to use the base price",
                )
            if product_name is None:
                continue
            if (
                slugify(product_name) not in sheet_products
                and self.catalogue.find_product(product_name) is None
            ):
                self._problem(row, "Product name", f'"{product_name}" is not on the Products sheet')
                continue

            self._check_compare_at(row, sheet_products.get(slugify(product_name)))

            key = self.catalogue.product_key(product_name)
            existing = self.catalogue.variants.get(sku) if sku else None
            if existing is not None and existing.product_id != key:
                self._problem(row, "SKU", f'"{sku}" already belongs to "{existing.product.name}"')
            if row["Size"] is not None:
                combination = (key, row["Size"], row["Shade"])
                if combination in combinations:
                    self._problem(
                        row,
                        "Size",
                        f'"{product_name}" already has a variant in {row["Size"]}, '
                        f"{row['Shade'] or 'no shade'} on row {combinations[combination]}",
                    )
                combinations.setdefault(combination, row.number)

        for variant in self.catalogue.variants.values():
            if variant.sku in skus:
                continue
            combination = (
                variant.product_id,
                variant.size.name,
                variant.shade.name if variant.shade else None,
            )
            if combination in combinations:
                self.plan.problems.append(
                    Problem(
                        VARIANTS.title,
                        f'"{variant.product.name}" already has a variant in the shop in this '
                        f'size and shade, SKU "{variant.sku}"',
                        combinations[combination],
                        "Size",
                    )
                )

    def _check_compare_at(self, row: Row, product_row: Row | None) -> None:
        compare_at = row["Compare-at price (NPR)"]
        if compare_at is None:
            return
        price = row["Price override (NPR)"]
        existing = self.catalogue.variants.get(row["SKU"]) if row["SKU"] else None
        if not row.provides("Price override (NPR)") and existing is not None:
            price = existing.price_override
        if price is None:
            # The sheet's base price, when the product is on it, is the one the
            # import is about to write.
            if product_row is not None:
                price = product_row["Base price (NPR)"]
            elif product := self.catalogue.find_product(row["Product name"]):
                price = product.base_price
        if price is not None and compare_at <= price:
            self._problem(
                row,
                "Compare-at price (NPR)",
                f"must be more than the price, {price}; leave it blank if the variant "
                "is not on sale",
            )

    def _check_published_products_have_variants(self) -> None:
        with_variants: set[ProductKey] = {
            variant.product_id for variant in self.catalogue.variants.values()
        }
        with_variants |= {
            self.catalogue.product_key(row["Product name"])
            for row in self.rows[VARIANTS]
            if row["Product name"]
        }
        for row in self.rows[PRODUCTS]:
            name = row["Product name"]
            if row["Published"] and name and self.catalogue.product_key(name) not in with_variants:
                self._problem(
                    row,
                    "Published",
                    f"{ProductHasNoVariants.message} Add one on the Variants sheet, "
                    "or set Published to No",
                )
