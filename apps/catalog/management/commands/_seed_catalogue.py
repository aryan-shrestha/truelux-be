from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class BrandSpec:
    name: str
    slug: str
    code: str
    description: str
    palette: tuple[str, str]


@dataclass(frozen=True)
class VariantSpec:
    size: str
    shade: str | None
    stock: int
    price_override: Decimal | None = None


@dataclass(frozen=True)
class ProductSpec:
    name: str
    slug: str
    brand: str
    category: str
    base_price: Decimal
    description: str
    variants: tuple[VariantSpec, ...]
    image_count: int = 1
    is_published: bool = True
    skin_types: tuple[str, ...] = ()
    skin_feel: str = ""
    key_ingredients: str = ""


def sized(*sizes: tuple[str, int] | tuple[str, int, str]) -> tuple[VariantSpec, ...]:
    return tuple(
        VariantSpec(size[0], None, size[1], Decimal(size[2]) if len(size) == 3 else None)
        for size in sizes
    )


def shaded(size: str, *shades: tuple[str, int]) -> tuple[VariantSpec, ...]:
    return tuple(VariantSpec(size, shade, stock) for shade, stock in shades)


BRANDS: tuple[BrandSpec, ...] = (
    BrandSpec(
        "Lumière", "lumiere", "LUM", "French-inspired complexion care.", ("#F3E3D3", "#C9A48A")
    ),
    BrandSpec(
        "Verde Botanics",
        "verde-botanics",
        "VRD",
        "Plant-led skincare with short ingredient lists.",
        ("#E4EDDC", "#7E9B6E"),
    ),
    BrandSpec(
        "Kaya Rose",
        "kaya-rose",
        "KYR",
        "Rose-infused skincare and makeup from the Himalayan foothills.",
        ("#F6DDE0", "#B5656B"),
    ),
    BrandSpec(
        "Nordic Dew",
        "nordic-dew",
        "NRD",
        "Cold-water hydration for every skin type.",
        ("#E3EEF4", "#7D9DB3"),
    ),
    BrandSpec(
        "Saffron & Co.",
        "saffron-co",
        "SAF",
        "Ayurvedic rituals, modern formulas.",
        ("#FBE7C6", "#D98E2B"),
    ),
    BrandSpec("Aurum", "aurum", "AUR", "Gold-standard luxury treatments.", ("#F5EBD0", "#B8923A")),
    BrandSpec(
        "Mistral",
        "mistral",
        "MST",
        "Weightless makeup for warm climates.",
        ("#EDE7F2", "#8C7AA6"),
    ),
    BrandSpec(
        "Bloom Theory",
        "bloom-theory",
        "BLM",
        "Clinical actives, gentle textures.",
        ("#FCE9E2", "#D9826A"),
    ),
)

SIZES: tuple[tuple[str, str], ...] = (
    ("3.5 g", "3-5-g"),
    ("4 g", "4-g"),
    ("6 ml", "6-ml"),
    ("8 g", "8-g"),
    ("10 ml", "10-ml"),
    ("15 ml", "15-ml"),
    ("30 ml", "30-ml"),
    ("50 ml", "50-ml"),
    ("100 ml", "100-ml"),
    ("150 ml", "150-ml"),
    ("200 ml", "200-ml"),
    ("200 g", "200-g"),
    ("250 ml", "250-ml"),
    ("400 ml", "400-ml"),
    ("One size", "one-size"),
)

SHADES: tuple[tuple[str, str, str], ...] = (
    ("Porcelain", "porcelain", "#F3D9C6"),
    ("Ivory", "ivory", "#EDCDB2"),
    ("Warm Beige", "warm-beige", "#D8A47F"),
    ("Honey", "honey", "#C68E5E"),
    ("Caramel", "caramel", "#A86B42"),
    ("Mocha", "mocha", "#7A4B2E"),
    ("Rose Nude", "rose-nude", "#C98B83"),
    ("Dusty Rose", "dusty-rose", "#B5656B"),
    ("Mauve", "mauve", "#9C6B82"),
    ("Brick Red", "brick-red", "#9E3B2F"),
    ("Classic Red", "classic-red", "#B3122E"),
    ("Berry", "berry", "#7D2748"),
    ("Soft Peach", "soft-peach", "#F4A988"),
    ("Petal Pink", "petal-pink", "#E8919B"),
    ("Terracotta", "terracotta", "#C0664A"),
    ("Plum", "plum", "#8E4A5C"),
    ("Champagne", "champagne", "#F1D3A1"),
    ("Rose Gold", "rose-gold", "#E0A98E"),
    ("Bronze", "bronze", "#B7804F"),
    ("Jet Black", "jet-black", "#1B1B1B"),
    ("Espresso", "espresso", "#3B2A20"),
    ("Taupe", "taupe", "#8B7361"),
    ("Soft Brown", "soft-brown", "#6E4F3A"),
)

SKIN_TYPES: tuple[tuple[str, str], ...] = (
    ("Normal", "normal"),
    ("Dry", "dry"),
    ("Oily", "oily"),
    ("Combination", "combination"),
    ("Sensitive", "sensitive"),
    ("Mature", "mature"),
)

# Mirrors the storefront design's mega-menu.
CATEGORIES: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Skincare",
        "skincare",
        (
            ("Cleanse", "cleanse"),
            ("Exfoliate", "exfoliate"),
            ("Treat & Masque", "treat-masque"),
            ("Tone", "tone"),
            ("Hydrate", "hydrate"),
            ("Eyes & Lips", "eyes-lips"),
            ("Sun Care", "sun-care"),
        ),
    ),
    ("Makeup", "makeup", (("Face", "face"), ("Eyes", "eyes"), ("Lips", "lips"))),
    (
        "Body",
        "body",
        (
            ("Creams, Oils & Scrubs", "creams-oils-scrubs"),
            ("Shower & Bath", "shower-bath"),
            ("Balms", "balms"),
            ("Hands & Feet", "hands-feet"),
            ("Sun Protection", "sun-protection"),
        ),
    ),
    ("Fragrance", "fragrance", (("Perfume", "perfume"), ("Essential Oils", "essential-oils"))),
    ("Haircare", "haircare", ()),
)

# Categories an earlier version of this seed created. `--flush` removes them when
# empty, so a reseeded database shows only the tree above.
RETIRED_CATEGORY_SLUGS: tuple[str, ...] = ("cleansers", "serums", "moisturisers")

# Deliberately uneven, so the storefront meets the awkward shapes a merchant can
# produce: a product with no image, one that is sold out, one unpublished, several
# with a price_override on the larger size, and variants at or under the low-stock
# threshold for the admin dashboard.
PRODUCTS: tuple[ProductSpec, ...] = (
    ProductSpec(
        "Green Tea Gel Cleanser",
        "green-tea-gel-cleanser",
        "verde-botanics",
        "cleanse",
        Decimal("1450.00"),
        "A low-foam gel that lifts sunscreen and oil without the tight feel afterwards.",
        sized(("150-ml", 24), ("250-ml", 12, "2100.00")),
        image_count=2,
        skin_types=("oily", "combination", "normal"),
        skin_feel="Clean, fresh, never tight",
        key_ingredients=(
            "Water (Aqua), Camellia Sinensis (Green Tea) Leaf Extract, Coco-Glucoside, "
            "Glycerin, Panthenol"
        ),
    ),
    ProductSpec(
        "Rose Milk Cleanser",
        "rose-milk-cleanser",
        "kaya-rose",
        "cleanse",
        Decimal("1850.00"),
        "A creamy cleanser with rose water and oat milk for dry and sensitive skin.",
        sized(("200-ml", 18)),
        skin_types=("dry", "sensitive", "mature"),
        skin_feel="Soft, cushioned, comforted",
        key_ingredients=(
            "Rosa Damascena Flower Water, Avena Sativa (Oat) Kernel Extract, "
            "Butyrospermum Parkii (Shea) Butter, Glycerin"
        ),
    ),
    ProductSpec(
        "Glacier Clay Cleanser",
        "glacier-clay-cleanser",
        "nordic-dew",
        "cleanse",
        Decimal("1650.00"),
        "White clay and cold-pressed birch sap to clear congested pores.",
        sized(("100-ml", 3)),
        skin_types=("oily", "combination"),
        skin_feel="Purified, matte, refreshed",
        key_ingredients=("Betula Alba (Birch) Juice, Kaolin, Bentonite, Zinc PCA, Salicylic Acid"),
    ),
    ProductSpec(
        "Micellar Cleansing Water",
        "micellar-cleansing-water",
        "lumiere",
        "cleanse",
        Decimal("1350.00"),
        "Removes makeup, including mascara, in one pass. No rinse needed.",
        sized(("200-ml", 30), ("400-ml", 14, "2200.00")),
        skin_types=("normal", "dry", "oily", "sensitive"),
        skin_feel="Fresh, clean, residue-free",
        key_ingredients="Water (Aqua), Poloxamer 184, Glycerin, Hexylene Glycol, Allantoin",
    ),
    ProductSpec(
        "Papaya Enzyme Polish",
        "papaya-enzyme-polish",
        "verde-botanics",
        "exfoliate",
        Decimal("1750.00"),
        "A creamy enzyme exfoliant that dissolves dullness without grains or scrubbing.",
        sized(("50-ml", 16)),
        skin_types=("normal", "dry", "sensitive"),
        skin_feel="Smooth, bright, gently renewed",
        key_ingredients=(
            "Water (Aqua), Carica Papaya (Papaya) Fruit Extract, Papain, Lactic Acid, "
            "Aloe Barbadensis Leaf Juice"
        ),
    ),
    ProductSpec(
        "Glycolic Resurfacing Pads",
        "glycolic-resurfacing-pads",
        "bloom-theory",
        "exfoliate",
        Decimal("2300.00"),
        "Sixty pre-soaked pads with 7% glycolic acid for a weekly reset.",
        sized(("one-size", 11)),
        skin_types=("oily", "combination", "mature"),
        skin_feel="Refined, even, luminous",
        key_ingredients=(
            "Water (Aqua), Glycolic Acid, Sodium Hydroxide, Hamamelis Virginiana "
            "(Witch Hazel) Water, Panthenol"
        ),
    ),
    ProductSpec(
        "24K Radiance Serum",
        "24k-radiance-serum",
        "aurum",
        "treat-masque",
        Decimal("4800.00"),
        "Colloidal gold and vitamin C in a silky serum for dull, tired skin.",
        sized(("30-ml", 9), ("50-ml", 4, "7200.00")),
        image_count=2,
        skin_types=("normal", "dry", "mature"),
        skin_feel="Radiant, supple, awakened",
        key_ingredients=(
            "Water (Aqua), Colloidal Gold, 3-O-Ethyl Ascorbic Acid, Sodium Hyaluronate, Tocopherol"
        ),
    ),
    ProductSpec(
        "Hyaluronic Hydra Serum",
        "hyaluronic-hydra-serum",
        "nordic-dew",
        "treat-masque",
        Decimal("2900.00"),
        "Three weights of hyaluronic acid to plump every layer of the skin.",
        sized(("30-ml", 22)),
        skin_types=("normal", "dry", "oily", "combination"),
        skin_feel="Plump, dewy, quenched",
        key_ingredients=(
            "Water (Aqua), Sodium Hyaluronate, Hydrolyzed Hyaluronic Acid, "
            "Sodium Acetylated Hyaluronate, Panthenol"
        ),
    ),
    ProductSpec(
        "Niacinamide 10% Serum",
        "niacinamide-10-serum",
        "verde-botanics",
        "treat-masque",
        Decimal("1950.00"),
        "Evens tone and refines the look of pores. Layers under any moisturiser.",
        sized(("30-ml", 27)),
        skin_types=("oily", "combination"),
        skin_feel="Balanced, refined, shine-free",
        key_ingredients="Water (Aqua), Niacinamide, Zinc PCA, Tamarindus Indica Seed Gum",
    ),
    ProductSpec(
        "Saffron Glow Oil",
        "saffron-glow-oil",
        "saffron-co",
        "treat-masque",
        Decimal("3400.00"),
        "Kashmiri saffron in a light facial oil. Sold out until the next harvest.",
        sized(("30-ml", 0)),
        skin_types=("dry", "mature"),
        skin_feel="Nourished, glowing, silky",
        key_ingredients=(
            "Prunus Amygdalus Dulcis (Sweet Almond) Oil, Crocus Sativus (Saffron) Flower "
            "Extract, Santalum Album (Sandalwood) Oil, Tocopherol"
        ),
    ),
    ProductSpec(
        "Witch Hazel Balancing Toner",
        "witch-hazel-balancing-toner",
        "verde-botanics",
        "tone",
        Decimal("1250.00"),
        "An alcohol-free toner that calms redness and takes the shine off by noon.",
        sized(("150-ml", 20)),
        skin_types=("oily", "combination", "sensitive"),
        skin_feel="Soothed, balanced, refreshed",
        key_ingredients=(
            "Water (Aqua), Hamamelis Virginiana (Witch Hazel) Water, Niacinamide, "
            "Centella Asiatica Extract"
        ),
    ),
    ProductSpec(
        "Rose Water Toner",
        "rose-water-toner",
        "kaya-rose",
        "tone",
        Decimal("1100.00"),
        "Steam-distilled Damask rose water in a fine mist.",
        sized(("100-ml", 25), ("200-ml", 9, "1800.00")),
        skin_types=("normal", "dry", "sensitive"),
        skin_feel="Refreshed, hydrated, calm",
        key_ingredients="Rosa Damascena Flower Water, Glycerin, Sodium PCA, Allantoin",
    ),
    ProductSpec(
        "Rosehip Night Cream",
        "rosehip-night-cream",
        "kaya-rose",
        "hydrate",
        Decimal("3200.00"),
        "A rich overnight cream with rosehip oil and bakuchiol.",
        sized(("50-ml", 11)),
        skin_types=("dry", "mature"),
        skin_feel="Nourished, cushioned, restored",
        key_ingredients=(
            "Water (Aqua), Rosa Canina (Rosehip) Fruit Oil, Bakuchiol, Squalane, Ceramide NP"
        ),
    ),
    ProductSpec(
        "Arctic Water Cream",
        "arctic-water-cream",
        "nordic-dew",
        "hydrate",
        Decimal("2750.00"),
        "A gel-cream that sinks in instantly. Made for humid summers.",
        sized(("50-ml", 16)),
        skin_types=("normal", "oily", "combination"),
        skin_feel="Light, cool, weightless",
        key_ingredients=(
            "Betula Alba (Birch) Juice, Glycerin, Sodium Hyaluronate, Betaine, Allantoin"
        ),
    ),
    ProductSpec(
        "Peptide Barrier Cream",
        "peptide-barrier-cream",
        "bloom-theory",
        "hydrate",
        Decimal("3600.00"),
        "Not launched yet. If this appears in the public API, visibility scoping is broken.",
        sized(("50-ml", 20)),
        is_published=False,
        skin_types=("sensitive", "mature"),
        skin_feel="Calm, resilient, comfortable",
        key_ingredients=(
            "Water (Aqua), Palmitoyl Tripeptide-1, Ceramide NP, Cholesterol, Squalane"
        ),
    ),
    ProductSpec(
        "Caffeine Eye Cream",
        "caffeine-eye-cream",
        "nordic-dew",
        "eyes-lips",
        Decimal("2200.00"),
        "A cooling eye cream that de-puffs in the morning and hydrates at night.",
        sized(("15-ml", 14)),
        skin_types=("normal", "dry", "sensitive", "mature"),
        skin_feel="Awake, smooth, de-puffed",
        key_ingredients=(
            "Water (Aqua), Caffeine, Acetyl Hexapeptide-8, Sodium Hyaluronate, "
            "Cucumis Sativus (Cucumber) Fruit Extract"
        ),
    ),
    ProductSpec(
        "Beeswax Lip Balm",
        "beeswax-lip-balm",
        "verde-botanics",
        "eyes-lips",
        Decimal("450.00"),
        "Beeswax, shea and calendula. Nothing else.",
        sized(("4-g", 60)),
        skin_types=("dry", "sensitive"),
        skin_feel="Soft, protected, smooth",
        key_ingredients=(
            "Cera Alba (Beeswax), Butyrospermum Parkii (Shea) Butter, "
            "Calendula Officinalis Flower Extract"
        ),
    ),
    ProductSpec(
        "Daily Veil SPF 50",
        "daily-veil-spf-50",
        "lumiere",
        "sun-care",
        Decimal("2400.00"),
        "An invisible, broad-spectrum sunscreen that wears well under makeup.",
        sized(("50-ml", 40)),
        image_count=2,
        skin_types=("normal", "oily", "combination", "sensitive"),
        skin_feel="Invisible, light, protected",
        key_ingredients=(
            "Water (Aqua), Ethylhexyl Methoxycinnamate, Bis-Ethylhexyloxyphenol "
            "Methoxyphenyl Triazine, Niacinamide, Tocopherol"
        ),
    ),
    ProductSpec(
        "Mineral Shield SPF 30",
        "mineral-shield-spf-30",
        "bloom-theory",
        "sun-care",
        Decimal("2100.00"),
        "A zinc-only sunscreen with a sheer tint that leaves no white cast.",
        sized(("50-ml", 5)),
        skin_types=("dry", "sensitive"),
        skin_feel="Calm, comfortable, even",
        key_ingredients="Zinc Oxide, Caprylic/Capric Triglyceride, Squalane, Iron Oxides",
    ),
    ProductSpec(
        "Silk Foundation",
        "silk-foundation",
        "lumiere",
        "face",
        Decimal("3200.00"),
        "Medium coverage with a satin finish that lasts through a Kathmandu afternoon.",
        shaded(
            "30-ml",
            ("porcelain", 8),
            ("ivory", 12),
            ("warm-beige", 2),
            ("honey", 10),
            ("caramel", 6),
            ("mocha", 0),
        ),
        image_count=2,
    ),
    ProductSpec(
        "Second Skin Concealer",
        "second-skin-concealer",
        "bloom-theory",
        "face",
        Decimal("1900.00"),
        "Creamy, crease-proof coverage for under-eyes and blemishes.",
        shaded(
            "10-ml",
            ("porcelain", 7),
            ("ivory", 9),
            ("warm-beige", 5),
            ("honey", 11),
            ("caramel", 4),
        ),
    ),
    ProductSpec(
        "Cloud Blush",
        "cloud-blush",
        "mistral",
        "face",
        Decimal("1750.00"),
        "A whipped cream blush that blends out with fingertips.",
        shaded("4-g", ("soft-peach", 14), ("petal-pink", 9), ("terracotta", 6), ("plum", 3)),
    ),
    ProductSpec(
        "Golden Hour Highlighter",
        "golden-hour-highlighter",
        "aurum",
        "face",
        Decimal("2600.00"),
        "A finely milled pressed highlighter with a wet-look sheen.",
        shaded("8-g", ("champagne", 10), ("rose-gold", 8), ("bronze", 5)),
    ),
    ProductSpec(
        "Featherlight Mascara",
        "featherlight-mascara",
        "mistral",
        "eyes",
        Decimal("1450.00"),
        "Lengthens without clumps and survives monsoon humidity.",
        shaded("10-ml", ("jet-black", 25), ("espresso", 12)),
    ),
    ProductSpec(
        "Precision Brow Pencil",
        "precision-brow-pencil",
        "bloom-theory",
        "eyes",
        Decimal("1100.00"),
        "An ultra-fine tip for hair-like strokes, with a spoolie on the other end.",
        shaded("one-size", ("taupe", 13), ("soft-brown", 15), ("espresso", 9)),
    ),
    ProductSpec(
        "Kohl Kajal",
        "kohl-kajal",
        "saffron-co",
        "eyes",
        Decimal("850.00"),
        "Intense black kajal with camphor and almond oil.",
        shaded("one-size", ("jet-black", 45)),
    ),
    ProductSpec(
        "Desert Dusk Eyeshadow Palette",
        "desert-dusk-eyeshadow-palette",
        "aurum",
        "eyes",
        Decimal("4200.00"),
        "Twelve warm mattes and shimmers, from sand to smoked copper.",
        sized(("one-size", 7)),
    ),
    ProductSpec(
        "Velvet Matte Lipstick",
        "velvet-matte-lipstick",
        "kaya-rose",
        "lips",
        Decimal("1650.00"),
        "Full-pigment matte that stays comfortable all day.",
        shaded(
            "3-5-g",
            ("rose-nude", 18),
            ("dusty-rose", 12),
            ("mauve", 9),
            ("brick-red", 4),
            ("classic-red", 20),
            ("berry", 7),
        ),
        image_count=2,
    ),
    ProductSpec(
        "Satin Lip Crayon",
        "satin-lip-crayon",
        "mistral",
        "lips",
        Decimal("1400.00"),
        "A twist-up crayon with a soft satin finish.",
        shaded("3-5-g", ("rose-nude", 10), ("brick-red", 6), ("classic-red", 8), ("berry", 2)),
    ),
    ProductSpec(
        "Glass Lip Oil",
        "glass-lip-oil",
        "lumiere",
        "lips",
        Decimal("1250.00"),
        "A non-sticky tinted oil for a high-shine finish.",
        sized(("6-ml", 19)),
    ),
    ProductSpec(
        "Amla Bhringraj Hair Oil",
        "amla-bhringraj-hair-oil",
        "saffron-co",
        "haircare",
        Decimal("950.00"),
        "A traditional pre-wash oil for stronger, shinier hair.",
        sized(("100-ml", 26), ("200-ml", 13, "1500.00")),
    ),
    ProductSpec(
        "Argan Repair Shampoo",
        "argan-repair-shampoo",
        "verde-botanics",
        "haircare",
        Decimal("1350.00"),
        "A sulphate-free shampoo for dry, chemically treated hair.",
        sized(("250-ml", 21)),
    ),
    ProductSpec(
        "Silk Protein Conditioner",
        "silk-protein-conditioner",
        "nordic-dew",
        "haircare",
        Decimal("1400.00"),
        "Detangles and smooths without weighing fine hair down.",
        sized(("250-ml", 17)),
    ),
    ProductSpec(
        "Oud Noir Eau de Parfum",
        "oud-noir-eau-de-parfum",
        "aurum",
        "perfume",
        Decimal("8500.00"),
        "Smoky oud, saffron and leather. Evening wear.",
        sized(("50-ml", 6), ("100-ml", 3, "13500.00")),
        image_count=2,
    ),
    ProductSpec(
        "Sea Salt & Neroli Eau de Toilette",
        "sea-salt-neroli-eau-de-toilette",
        "mistral",
        "perfume",
        Decimal("5200.00"),
        "A bright, salty citrus for hot days.",
        sized(("50-ml", 10), ("100-ml", 5, "7800.00")),
    ),
    ProductSpec(
        "Damask Rose Eau de Parfum",
        "damask-rose-eau-de-parfum",
        "kaya-rose",
        "perfume",
        Decimal("6800.00"),
        "Distilled Damask rose over a soft musk base.",
        sized(("50-ml", 8), ("100-ml", 4, "10500.00")),
    ),
    ProductSpec(
        "Lavender Essential Oil",
        "lavender-essential-oil",
        "verde-botanics",
        "essential-oils",
        Decimal("1200.00"),
        "Steam-distilled lavender for a pillow, a bath or a diffuser.",
        sized(("10-ml", 30)),
    ),
    ProductSpec(
        "Himalayan Cedarwood Oil",
        "himalayan-cedarwood-oil",
        "saffron-co",
        "essential-oils",
        Decimal("1450.00"),
        "Deodar cedarwood from the western Himalaya: woody, warm and grounding.",
        sized(("10-ml", 18)),
    ),
    ProductSpec(
        "Shea Body Butter",
        "shea-body-butter",
        "bloom-theory",
        "creams-oils-scrubs",
        Decimal("1800.00"),
        "Whipped shea and ceramides for very dry skin.",
        sized(("200-g", 15)),
        # No image at all: the card and the gallery both have to survive it.
        image_count=0,
        skin_types=("dry", "mature"),
        skin_feel="Rich, supple, deeply nourished",
        key_ingredients=(
            "Butyrospermum Parkii (Shea) Butter, Water (Aqua), Glycerin, Ceramide NP, Urea"
        ),
    ),
    ProductSpec(
        "Ubtan Body Scrub",
        "ubtan-body-scrub",
        "saffron-co",
        "creams-oils-scrubs",
        Decimal("1550.00"),
        "Chickpea flour, turmeric and sandalwood in a gentle polish.",
        sized(("200-g", 12)),
        skin_types=("normal", "oily", "combination"),
        skin_feel="Polished, smooth, bright",
        key_ingredients=(
            "Cicer Arietinum (Chickpea) Seed Powder, Curcuma Longa (Turmeric) Root Powder, "
            "Santalum Album (Sandalwood) Powder, Prunus Amygdalus Dulcis (Sweet Almond) Oil"
        ),
    ),
    ProductSpec(
        "Birch Body Wash",
        "birch-body-wash",
        "nordic-dew",
        "shower-bath",
        Decimal("1100.00"),
        "A fresh, low-foam wash with birch sap and glycerin.",
        sized(("250-ml", 28)),
        skin_types=("normal", "oily"),
        skin_feel="Fresh, clean, invigorated",
        key_ingredients=(
            "Water (Aqua), Betula Alba (Birch) Juice, Sodium Cocoyl Isethionate, Glycerin"
        ),
    ),
    ProductSpec(
        "Oat Milk Bath Soak",
        "oat-milk-bath-soak",
        "kaya-rose",
        "shower-bath",
        Decimal("1300.00"),
        "Colloidal oat and rose petals that turn a bath milky and soft.",
        sized(("200-g", 13)),
        skin_types=("dry", "sensitive"),
        skin_feel="Calm, soft, comforted",
        key_ingredients=(
            "Avena Sativa (Oat) Kernel Flour, Magnesium Sulfate, "
            "Rosa Damascena Flower, Sodium Bicarbonate"
        ),
    ),
    ProductSpec(
        "Arnica Muscle Balm",
        "arnica-muscle-balm",
        "saffron-co",
        "balms",
        Decimal("1150.00"),
        "A warming balm for tired shoulders after a long trek.",
        sized(("50-ml", 17)),
        skin_types=("normal", "dry"),
        skin_feel="Warm, relieved, relaxed",
        key_ingredients=(
            "Helianthus Annuus (Sunflower) Seed Oil, Cera Alba (Beeswax), "
            "Arnica Montana Flower Extract, Menthol, Camphor"
        ),
    ),
    ProductSpec(
        "Calendula Rescue Balm",
        "calendula-rescue-balm",
        "verde-botanics",
        "balms",
        Decimal("950.00"),
        "One tin for cracked heels, dry cuticles and wind-burnt cheeks.",
        sized(("50-ml", 22)),
        skin_types=("dry", "sensitive"),
        skin_feel="Soothed, protected, repaired",
        key_ingredients=(
            "Olea Europaea (Olive) Fruit Oil, Cera Alba (Beeswax), "
            "Calendula Officinalis Flower Extract, Bisabolol"
        ),
    ),
    ProductSpec(
        "Rose Hand Cream",
        "rose-hand-cream",
        "kaya-rose",
        "hands-feet",
        Decimal("850.00"),
        "A fast-absorbing hand cream that leaves no greasy film.",
        sized(("50-ml", 34)),
        skin_types=("normal", "dry"),
        skin_feel="Soft, velvety, non-greasy",
        key_ingredients=(
            "Water (Aqua), Rosa Damascena Flower Water, Glycerin, "
            "Butyrospermum Parkii (Shea) Butter, Dimethicone"
        ),
    ),
    ProductSpec(
        "Peppermint Foot Cream",
        "peppermint-foot-cream",
        "nordic-dew",
        "hands-feet",
        Decimal("1050.00"),
        "Urea and peppermint to soften heels and cool tired feet.",
        sized(("100-ml", 4)),
        skin_types=("normal", "dry"),
        skin_feel="Cool, soft, refreshed",
        key_ingredients="Water (Aqua), Urea, Glycerin, Mentha Piperita (Peppermint) Oil, Menthol",
    ),
    ProductSpec(
        "Sheer Body Sunscreen SPF 50",
        "sheer-body-sunscreen-spf-50",
        "lumiere",
        "sun-protection",
        Decimal("2600.00"),
        "A dry-touch body lotion that rubs in clear and survives a swim.",
        sized(("150-ml", 19)),
        skin_types=("normal", "oily", "combination"),
        skin_feel="Dry-touch, light, protected",
        key_ingredients=(
            "Water (Aqua), Homosalate, Ethylhexyl Salicylate, Butyl Methoxydibenzoylmethane, "
            "Tocopherol"
        ),
    ),
    ProductSpec(
        "After-Sun Aloe Gel",
        "after-sun-aloe-gel",
        "nordic-dew",
        "sun-protection",
        Decimal("1250.00"),
        "A cooling gel for skin that stayed out too long.",
        sized(("200-ml", 21)),
        skin_types=("normal", "dry", "sensitive"),
        skin_feel="Cooled, soothed, hydrated",
        key_ingredients=("Aloe Barbadensis Leaf Juice, Glycerin, Panthenol, Allantoin, Menthol"),
    ),
)
