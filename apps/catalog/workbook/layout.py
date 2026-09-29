from dataclasses import dataclass
from enum import StrEnum

type CellValue = str | int | float | None

FONT_NAME = "Arial"
HEADER_ROW = 1
EXAMPLE_ROW = 2
FIRST_DATA_ROW = 3
LAST_VALIDATED_ROW = 1000

YES = "Yes"
NO = "No"


class Kind(StrEnum):
    TEXT = "text"
    WHOLE = "whole number"
    PRICE = "price"
    YES_NO = "yes/no"
    HEX = "hex colour"


@dataclass(frozen=True)
class Column:
    header: str
    comment: str
    width: int
    kind: Kind = Kind.TEXT
    required: bool = False
    max_length: int | None = None
    # A dropdown of the Name column of this sheet.
    choices_from: str | None = None
    # Part of how a row is matched to the database, so its header must be present
    # even though its cells may be blank.
    identifies: bool = False


@dataclass(frozen=True)
class Sheet:
    title: str
    columns: tuple[Column, ...]
    example: tuple[CellValue, ...]

    def column(self, header: str) -> Column:
        return next(column for column in self.columns if column.header == header)


def _sort_order() -> Column:
    return Column(
        "Sort order",
        "Optional. A whole number; lower numbers are listed first. Blank means 0.",
        12,
        kind=Kind.WHOLE,
    )


BRANDS = Sheet(
    "Brands",
    (
        Column(
            "Name",
            "Required. The brand's name exactly as customers should see it. Each brand once.",
            28,
            required=True,
            max_length=150,
        ),
        Column("Description", "Optional. One or two sentences about the brand.", 50),
        Column(
            "Logo file",
            "Optional. The file name of the logo in the images folder, e.g. "
            "glow-lab-logo.png. JPEG, PNG or WebP, 5 MB at most.",
            26,
        ),
        Column(
            "Active",
            "Optional. Yes or No. Blank means Yes. An inactive brand and all its "
            "products are hidden from the shop.",
            10,
            kind=Kind.YES_NO,
        ),
        _sort_order(),
    ),
    (
        "Glow Lab",
        "Korean-inspired skincare with gentle, fragrance-free formulas.",
        "glow-lab-logo.png",
        YES,
        1,
    ),
)

CATEGORIES = Sheet(
    "Categories",
    (
        Column(
            "Name",
            "Required. The category's name as it appears in the shop menu.",
            28,
            required=True,
            max_length=150,
        ),
        Column(
            "Parent category",
            "Optional. Blank makes this a top-level category. Otherwise pick a top-level "
            "category from this sheet: categories are one level deep only.",
            28,
            choices_from="Categories",
            identifies=True,
        ),
        _sort_order(),
    ),
    ("Serums", "Skincare", 3),
)

SHADES = Sheet(
    "Shades",
    (
        Column(
            "Name",
            "Required. The shade's name, e.g. Warm Honey. Each shade once.",
            24,
            required=True,
            max_length=50,
        ),
        Column(
            "Hex colour",
            "Required. The swatch colour as # followed by six characters, e.g. #D8A47F.",
            14,
            kind=Kind.HEX,
            required=True,
        ),
        _sort_order(),
    ),
    ("Warm Honey", "#D8A47F", 1),
)

SIZES = Sheet(
    "Sizes",
    (
        Column(
            "Name",
            'Required. A size as customers see it, e.g. "50 ml", "4 g" or "One size". '
            "Each size once.",
            20,
            required=True,
            max_length=50,
        ),
        _sort_order(),
    ),
    ("30 ml", 3),
)

SKIN_TYPES = Sheet(
    "Skin types",
    (
        Column(
            "Name",
            "Required. A skin type customers can shop by. Each skin type once.",
            20,
            required=True,
            max_length=50,
        ),
        _sort_order(),
    ),
    ("Acne-prone", 7),
)

PRODUCTS = Sheet(
    "Products",
    (
        Column(
            "Product name",
            "Required. The product's name without the brand. Each product once; the "
            "Variants sheet refers to it by this exact name.",
            34,
            required=True,
            max_length=200,
        ),
        Column(
            "Brand",
            "Required. A brand from the Brands sheet.",
            22,
            required=True,
            choices_from="Brands",
        ),
        Column(
            "Category",
            "Required. A category from the Categories sheet, usually a sub-category.",
            22,
            required=True,
            choices_from="Categories",
        ),
        Column(
            "Base price (NPR)",
            "Required. The price in rupees as a plain number, e.g. 2450 or 2450.50. "
            'No commas and no "Rs".',
            16,
            kind=Kind.PRICE,
            required=True,
        ),
        Column("Description", "Optional. The product description shown on its page.", 50),
        Column(
            "Skin types",
            "Optional. Names from the Skin types sheet, separated by commas, e.g. Dry, Sensitive.",
            24,
        ),
        Column(
            "Skin feel",
            "Optional. How it feels on the skin, e.g. Light, dewy, non-sticky.",
            28,
            max_length=200,
        ),
        Column("Key ingredients", "Optional. The ingredient list, separated by commas.", 40),
        Column(
            "Published",
            "Optional. Yes or No. Blank means No. Only published products appear in the "
            "shop, and a published product needs at least one variant.",
            11,
            kind=Kind.YES_NO,
        ),
        Column(
            "Image files",
            "Optional. File names in the images folder, separated by commas. The first "
            "is the main image. JPEG, PNG or WebP, 5 MB at most each.",
            40,
        ),
        Column(
            "Image alt text",
            "Optional. A short description of the images for screen readers.",
            30,
            max_length=255,
        ),
        _sort_order(),
    ),
    (
        "Hydrating Rose Serum",
        "Glow Lab",
        "Serums",
        2450,
        "A lightweight serum that hydrates and calms.",
        "Dry, Sensitive",
        "Light, dewy, non-sticky",
        "Water, Glycerin, Rosa Damascena Flower Water, Niacinamide",
        YES,
        "rose-serum-front.jpg, rose-serum-back.jpg",
        "Glow Lab Hydrating Rose Serum bottle",
        1,
    ),
)

VARIANTS = Sheet(
    "Variants",
    (
        Column(
            "Product name",
            "Required. A product from the Products sheet, spelled exactly the same.",
            34,
            required=True,
        ),
        Column(
            "SKU",
            "Required. Your stock code for this exact size and shade. Each SKU once.",
            22,
            required=True,
            max_length=64,
        ),
        Column(
            "Size",
            "Required. A size from the Sizes sheet.",
            14,
            required=True,
            choices_from="Sizes",
        ),
        Column(
            "Shade",
            "Optional. A shade from the Shades sheet. Blank means the product has no shade.",
            18,
            choices_from="Shades",
            identifies=True,
        ),
        Column(
            "Stock",
            "Required. How many are on the shelf, as a whole number.",
            10,
            kind=Kind.WHOLE,
            required=True,
        ),
        Column(
            "Price override (NPR)",
            "Optional. A price for this variant only, e.g. a larger size. Blank uses the "
            "product's base price.",
            18,
            kind=Kind.PRICE,
        ),
        Column(
            "Compare-at price (NPR)",
            "Optional. The old price, shown struck through to put this variant on sale. "
            "Must be more than the price the customer pays. Blank means not on sale.",
            20,
            kind=Kind.PRICE,
        ),
    ),
    ("Hydrating Rose Serum", "GL-ROSE-30", "30 ml", None, 24, None, None),
)

DATA_SHEETS = (BRANDS, CATEGORIES, SHADES, SIZES, SKIN_TYPES, PRODUCTS, VARIANTS)

READ_ME_TITLE = "Read me"

PREFILLED_SKIN_TYPES: tuple[tuple[CellValue, ...], ...] = (
    ("Normal", 1),
    ("Dry", 2),
    ("Oily", 3),
    ("Combination", 4),
    ("Sensitive", 5),
    ("Mature", 6),
)

READ_ME: tuple[tuple[str, str], ...] = (
    ("title", "TrueLux catalogue workbook"),
    (
        "text",
        "Fill in this workbook with everything the shop sells. We load it into the "
        "shop in one go, so every product, brand, size and shade you list here "
        "appears exactly as written.",
    ),
    ("heading", "How to fill it in"),
    ("text", "1. Start with Brands, Categories, Shades, Sizes and Skin types."),
    ("text", "2. Then list each product on Products."),
    (
        "text",
        "3. On Variants, add one row for every size and shade you sell of each "
        "product, with its SKU and stock.",
    ),
    (
        "text",
        "4. Put every image in one folder, and send the folder with this workbook.",
    ),
    ("heading", "Legend"),
    ("required", "Dark header: required. Every row needs a value in this column."),
    ("optional", "Grey header: optional. Leave it blank if it does not apply."),
    ("example", "Row 2 on every sheet is an example. It is ignored; start on row 3."),
    ("text", "Hover over a header to see what the column is for."),
    ("heading", "Rules"),
    (
        "text",
        "• Names must match exactly across sheets: a product's Brand must be spelled "
        "as on the Brands sheet. Use the dropdowns where there is one.",
    ),
    ("text", "• Yes/No columns take Yes or No."),
    (
        "text",
        '• Prices are in NPR, as plain numbers: 2450 or 2450.50, without commas or "Rs".',
    ),
    (
        "text",
        "• To put a variant on sale, lower its price and enter the old price as its "
        "Compare-at price. Clear the Compare-at price when the sale ends.",
    ),
    ("text", "• Hex colours are # followed by six characters, like #D8A47F."),
    (
        "text",
        "• Send all images in one folder. File names in the workbook must match the "
        "files exactly, including the extension (rose-serum-front.jpg). JPEG, PNG or "
        "WebP, up to 5 MB each.",
    ),
    (
        "text",
        "• The first image listed for a product is its main image.",
    ),
    ("heading", "Questions"),
    ("text", "Contact: [name], [phone], [email]"),
)
