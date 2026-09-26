from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cloudinary.exceptions
from django.core.files import File
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import Brand, Category, Product, Shade, Size, SkinType
from apps.catalog.services import (
    add_product_image,
    create_product,
    create_taxonomy_entry,
    create_variant,
    delete_product_image,
    set_variant_stock,
    update_product,
    update_taxonomy_entry,
    update_variant,
)
from apps.catalog.workbook.layout import (
    BRANDS,
    CATEGORIES,
    DATA_SHEETS,
    PRODUCTS,
    SHADES,
    SIZES,
    SKIN_TYPES,
    VARIANTS,
    Sheet,
)
from apps.catalog.workbook.reader import Problem, Row, read_workbook
from apps.catalog.workbook.validation import (
    Catalogue,
    CategoryKey,
    Plan,
    ProductKey,
    Validator,
    split_list,
)

# What a failed upload raises: the file could not be read, or Cloudinary refused it.
UPLOAD_ERRORS = (OSError, cloudinary.exceptions.Error)


@dataclass
class Tally:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    not_in_workbook: list[str] = field(default_factory=list)


@dataclass
class LogoUpload:
    brand: Brand
    path: Path


@dataclass
class ImageUpload:
    product: Product
    paths: list[Path]
    alt_text: str


@dataclass
class ImportReport:
    problems: list[Problem] = field(default_factory=list)
    tallies: dict[Sheet, Tally] = field(default_factory=lambda: {s: Tally() for s in DATA_SHEETS})
    logo_uploads: list[LogoUpload] = field(default_factory=list)
    image_uploads: list[ImageUpload] = field(default_factory=list)
    uploaded: int = 0
    upload_failures: list[str] = field(default_factory=list)

    @property
    def planned_uploads(self) -> int:
        return len(self.logo_uploads) + sum(len(job.paths) for job in self.image_uploads)


def import_catalogue(
    path: Path, *, images_dir: Path | None, replace_images: bool, dry_run: bool
) -> ImportReport:
    """Validates the whole workbook and writes nothing if any problem is found."""
    rows, problems = read_workbook(path)
    report = ImportReport(problems=problems)

    with transaction.atomic():
        catalogue = Catalogue()
        plan = Validator(
            rows, catalogue, images_dir=images_dir, replace_images=replace_images
        ).validate()
        report.problems.extend(plan.problems)
        if report.problems:
            return report
        _Writer(catalogue, plan, report).write()
        # A dry run takes the real write path, services and constraints included, so
        # its counts are the ones a real run would report.
        if dry_run:
            transaction.set_rollback(True)

    if not dry_run:
        _upload(report, replace_images=replace_images)
    return report


def _changes(instance: Any, desired: Mapping[str, Any]) -> dict[str, Any]:
    return {name: value for name, value in desired.items() if getattr(instance, name) != value}


class _Writer:
    def __init__(self, catalogue: Catalogue, plan: Plan, report: ImportReport) -> None:
        self.catalogue = catalogue
        self.plan = plan
        self.report = report
        self.products: dict[ProductKey, Product] = {}

    def rows(self, sheet: Sheet) -> list[Row]:
        return self.plan.rows[sheet]

    def write(self) -> None:
        brands = self._write_brands()
        shades = self._write_named(SHADES, Shade, self.catalogue.shades, ("hex_code", "Hex colour"))
        sizes = self._write_named(SIZES, Size, self.catalogue.sizes)
        skin_types = self._write_named(SKIN_TYPES, SkinType, self.catalogue.skin_types)
        categories = self._write_categories()
        to_publish = self._write_products(brands, categories, skin_types)
        self._write_variants(sizes, shades)
        for product in to_publish:
            update_product(product=product, fields={}, is_published=True)

    def _upsert[E: (Brand, Category, Shade, Size, SkinType)](
        self, sheet: Sheet, model: type[E], existing: E | None, fields: dict[str, Any]
    ) -> E:
        tally = self.report.tallies[sheet]
        if existing is None:
            tally.created += 1
            return create_taxonomy_entry(model=model, fields=fields)
        changed = _changes(existing, fields)
        if not changed:
            tally.unchanged += 1
            return existing
        tally.updated += 1
        return update_taxonomy_entry(entry=existing, fields=changed)

    def _note_missing(self, sheet: Sheet, names: set[str], written: set[str]) -> None:
        self.report.tallies[sheet].not_in_workbook = sorted(names - written)

    def _write_brands(self) -> dict[str, Brand]:
        brands = dict(self.catalogue.brands)
        for row in self.rows(BRANDS):
            fields = {
                "name": row["Name"],
                "description": row["Description"] or "",
                "is_active": row["Active"] is not False,
                "sort_order": row["Sort order"] or 0,
            }
            brand = self._upsert(BRANDS, Brand, brands.get(row["Name"]), fields)
            brands[brand.name] = brand
            if logo := self.plan.brand_logos.get(row.number):
                self.report.logo_uploads.append(LogoUpload(brand, logo))
        self._note_missing(
            BRANDS, set(self.catalogue.brands), {r["Name"] for r in self.rows(BRANDS)}
        )
        return brands

    def _write_named[E: (Shade, Size, SkinType)](
        self,
        sheet: Sheet,
        model: type[E],
        existing: dict[str, E],
        *extra: tuple[str, str],
    ) -> dict[str, E]:
        entries = dict(existing)
        for row in self.rows(sheet):
            fields = {"name": row["Name"], "sort_order": row["Sort order"] or 0}
            fields |= {field_name: row[header] for field_name, header in extra}
            entry = self._upsert(sheet, model, entries.get(row["Name"]), fields)
            entries[row["Name"]] = entry
        self._note_missing(sheet, set(existing), {row["Name"] for row in self.rows(sheet)})
        return entries

    def _write_categories(self) -> dict[CategoryKey, Category]:
        categories = dict(self.catalogue.categories)
        # Parents first, so a child's parent exists by the time it is written.
        rows = sorted(self.rows(CATEGORIES), key=lambda row: row["Parent category"] is not None)
        for row in rows:
            key = (row["Name"], row["Parent category"])
            fields = {"name": row["Name"], "sort_order": row["Sort order"] or 0}
            if row["Parent category"]:
                fields["parent"] = categories[(row["Parent category"], None)]
            category = self._upsert(CATEGORIES, Category, categories.get(key), fields)
            categories[key] = category
        self._note_missing(
            CATEGORIES,
            {_category_label(key) for key in self.catalogue.categories},
            {_category_label((row["Name"], row["Parent category"])) for row in rows},
        )
        return categories

    def _category(self, categories: dict[CategoryKey, Category], name: str) -> Category:
        matches = [category for key, category in categories.items() if key[0] == name]
        return matches[0]

    def _write_products(
        self,
        brands: dict[str, Brand],
        categories: dict[CategoryKey, Category],
        skin_types: dict[str, SkinType],
    ) -> list[Product]:
        tally = self.report.tallies[PRODUCTS]
        to_publish: list[Product] = []
        written: set[ProductKey] = set()
        for row in self.rows(PRODUCTS):
            name = row["Product name"]
            fields = {
                "name": name,
                "description": row["Description"] or "",
                "brand": brands[row["Brand"]],
                "category": self._category(categories, row["Category"]),
                "base_price": row["Base price (NPR)"],
                "sort_order": row["Sort order"] or 0,
                "skin_feel": row["Skin feel"] or "",
                "key_ingredients": row["Key ingredients"] or "",
            }
            wanted_skin_types = [
                skin_types[skin_type] for skin_type in split_list(row["Skin types"])
            ]
            publish = bool(row["Published"])
            product = self.catalogue.find_product(name)

            if product is None:
                product = create_product(
                    fields={**fields, "slug": slugify(name)}, skin_types=wanted_skin_types
                )
                tally.created += 1
                if publish:
                    to_publish.append(product)
            else:
                changed = _changes(product, fields)
                skin_types_changed = {s.pk for s in product.skin_types.all()} != {
                    s.pk for s in wanted_skin_types
                }
                publishing = publish and not product.is_published
                unpublishing = not publish and product.is_published
                if changed or skin_types_changed or unpublishing:
                    update_product(
                        product=product,
                        fields=changed,
                        is_published=False if unpublishing else None,
                        skin_types=wanted_skin_types if skin_types_changed else None,
                    )
                if changed or skin_types_changed or unpublishing or publishing:
                    tally.updated += 1
                else:
                    tally.unchanged += 1
                if publishing:
                    to_publish.append(product)

            key = self.catalogue.product_key(name)
            self.products[key] = product
            written.add(key)
            if paths := self.plan.product_images.get(row.number):
                self.report.image_uploads.append(
                    ImageUpload(product, paths, row["Image alt text"] or "")
                )

        tally.not_in_workbook = sorted(
            product.name
            for product in self.catalogue.products_by_slug.values()
            if product.pk not in written
        )
        return to_publish

    def _write_variants(self, sizes: dict[str, Size], shades: dict[str, Shade]) -> None:
        tally = self.report.tallies[VARIANTS]
        for row in self.rows(VARIANTS):
            fields = {
                "size": sizes[row["Size"]],
                "shade": shades[row["Shade"]] if row["Shade"] else None,
                "price_override": row["Price override (NPR)"],
            }
            stock = row["Stock"]
            variant = self.catalogue.variants.get(row["SKU"])
            if variant is None:
                product = self.products.get(self.catalogue.product_key(row["Product name"]))
                if product is None:
                    product = self.catalogue.find_product(row["Product name"])
                assert product is not None  # noqa: S101 - validation checked the reference
                variant = create_variant(product=product, fields={"sku": row["SKU"], **fields})
                if stock:
                    set_variant_stock(variant=variant, quantity=stock)
                tally.created += 1
                continue
            changed = _changes(variant, fields)
            stock_changed = variant.stock_quantity != stock
            if changed or stock_changed:
                update_variant(
                    variant=variant,
                    fields=changed,
                    stock_quantity=stock if stock_changed else None,
                )
                tally.updated += 1
            else:
                tally.unchanged += 1
        tally.not_in_workbook = sorted(
            set(self.catalogue.variants) - {row["SKU"] for row in self.rows(VARIANTS)}
        )


def _category_label(key: CategoryKey) -> str:
    name, parent = key
    return f"{parent} > {name}" if parent else name


def _upload(report: ImportReport, *, replace_images: bool) -> None:
    for logo in report.logo_uploads:
        try:
            with logo.path.open("rb") as handle:
                update_taxonomy_entry(
                    entry=logo.brand, fields={"logo": File(handle, name=logo.path.name)}
                )
            report.uploaded += 1
        except UPLOAD_ERRORS as error:
            report.upload_failures.append(f'Brand "{logo.brand.name}", "{logo.path.name}": {error}')

    for job in report.image_uploads:
        previous = list(job.product.images.all()) if replace_images else []
        has_primary = False
        failed = False
        for path in job.paths:
            try:
                with path.open("rb") as handle:
                    add_product_image(
                        product=job.product,
                        image=File(handle, name=path.name),
                        alt_text=job.alt_text,
                        is_primary=not has_primary,
                    )
            except UPLOAD_ERRORS as error:
                failed = True
                report.upload_failures.append(
                    f'Product "{job.product.name}", "{path.name}": {error}'
                )
                continue
            has_primary = True
            report.uploaded += 1
        # Keep the old images unless every new one arrived, so a failed upload never
        # leaves a product with fewer images than it had.
        if not failed:
            for image in previous:
                delete_product_image(image=image)
