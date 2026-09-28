from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class BrandSpec:
    name: str
    slug: str
    code: str
    description: str
    palette: tuple[str, str]
    # Tried in order; the logo falls back to a generated placeholder if none downloads.
    logo_urls: tuple[str, ...] = ()


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
    # One entry per product image, each a tuple of URLs tried in order.
    image_urls: tuple[tuple[str, ...], ...] = ()
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
        "Round Lab",
        "round-lab",
        "RDL",
        "Minimal skincare built around deep sea water from Ulleungdo's Dokdo islets.",
        ("#E6F0F7", "#7FA7C4"),
        logo_urls=("https://roundlab.co.kr/_dj/img/logo_.png",),
    ),
    BrandSpec(
        "COSRX",
        "cosrx",
        "CSX",
        "Science-first skincare known for its snail mucin and gentle acids.",
        ("#F2F2F2", "#3B3B3B"),
        logo_urls=(
            "https://www.cosrx.com/cdn/shop/files/facebookimg_dedb55e4-9ae0-421a-b480-dbcd570723aa_1200x1200.jpg?v=1612428226",
        ),
    ),
    BrandSpec(
        "Anua",
        "anua",
        "ANU",
        "Soothing skincare centred on heartleaf (houttuynia cordata).",
        ("#EEF3EA", "#6E8C63"),
        logo_urls=(
            "https://anua.com/cdn/shop/files/PNG_RGB_Primary_logo_ver2_2_255e833c-0e91-42df-96ca-0b7377ba7a8a.png?v=1779429699&width=600",
        ),
    ),
    BrandSpec(
        "Banila Co",
        "banila-co",
        "BNL",
        "Makers of the Clean It Zero cleansing balm.",
        ("#FBE3EA", "#D9738F"),
        logo_urls=(
            "https://banilausa.com/cdn/shop/files/BANILA_CO_Logotype_RGB_Black.png?v=1779099624&width=600",
            "https://upload.wikimedia.org/wikipedia/commons/c/cd/BanilaCo_logo.jpg",
        ),
    ),
    BrandSpec(
        "Isntree",
        "isntree",
        "IST",
        "Clean, gentle formulas from Korean natural ingredients.",
        ("#E9F2E6", "#5E8B55"),
        logo_urls=("https://www.isntree.com/web/upload/fixed_logo.png",),
    ),
    BrandSpec(
        "Beauty of Joseon",
        "beauty-of-joseon",
        "BOJ",
        "Skincare drawn from Joseon-era hanbang recipes: rice, ginseng and propolis.",
        ("#F5EEE3", "#B08D5C"),
        logo_urls=(
            "https://beautyofjoseon.com/cdn/shop/files/boj-logo-text-default.png?v=1765267757&width=480",
        ),
    ),
    BrandSpec(
        "SKIN1004",
        "skin1004",
        "SKN",
        "Skincare built on centella asiatica from Madagascar.",
        ("#F4EFE6", "#C9A46A"),
        logo_urls=(
            "https://www.skin1004.com/cdn/shop/files/SKIN1004_LOGO_300PX_30c77c72-0035-4b50-ba2c-f2c7a36a0d9d.png?v=1738771518&width=600",
            "https://www.skin1004.com/cdn/shop/files/logo_3ce60e3c-e671-45a3-b6b2-1c7f4cd826e5.png?v=1738772075",
        ),
    ),
    BrandSpec(
        "Laneige",
        "laneige",
        "LNG",
        "Amorepacific's hydration specialist, home of the Lip Sleeping Mask.",
        ("#E7EEFB", "#6A8CD6"),
        logo_urls=(
            "https://upload.wikimedia.org/wikipedia/commons/b/bc/LANEIGE_%EC%8B%A0%EA%B7%9C%EB%A1%9C%EA%B3%A0_%ED%95%98%EB%8A%98.jpg",
        ),
    ),
    BrandSpec(
        "Sulwhasoo",
        "sulwhasoo",
        "SWS",
        "Amorepacific's luxury house, rooted in Korean ginseng.",
        ("#F6EBDD", "#B7793A"),
        logo_urls=(
            "https://us.sulwhasoo.com/cdn/shop/files/SWS_Site_logo_Amber.png?v=1677003283&width=600",
            "https://upload.wikimedia.org/wikipedia/commons/5/56/%EC%84%A4%ED%99%94%EC%88%98_%EB%A1%9C%EA%B3%A0.png",
        ),
    ),
    BrandSpec(
        "Some By Mi",
        "some-by-mi",
        "SBM",
        "Targeted skincare for breakouts and dullness.",
        ("#E6F1EC", "#2F6B55"),
        logo_urls=(
            "https://www.somebymi.com/web/upload/category/editor/2025/08/19/35279b3e93f1e77a767fe2d5850a75e0.png",
        ),
    ),
    BrandSpec(
        "Illiyoon",
        "illiyoon",
        "ILY",
        "Hypoallergenic ceramide care for dry, sensitive skin.",
        ("#EEF4F8", "#7C9CB5"),
        logo_urls=(
            "https://www.illiyoon.com/web/upload/category/logo/v2_9ebddd997283793769b926556bf1ab08_cyQh2wrmmD_top.jpg",
        ),
    ),
    BrandSpec(
        "Torriden",
        "torriden",
        "TRD",
        "Hyaluronic-acid hydration for every skin type.",
        ("#E4F4F7", "#4FA3B8"),
        logo_urls=(
            "https://torriden.us/cdn/shop/files/logo-1200x628_efcc3821-85a6-4355-8239-11cb6dc80f30.png?v=1748999519&width=1200",
        ),
    ),
    BrandSpec(
        "Etude",
        "etude",
        "ETD",
        "Playful colour cosmetics and the gentle SoonJung skincare line.",
        ("#FCE6EF", "#D63C7A"),
        logo_urls=("https://int.etude.com/wp-content/uploads/2023/05/img_logo2023-1.png",),
    ),
    BrandSpec(
        "TIRTIR",
        "tirtir",
        "TIR",
        "Long-wear base makeup, famous for the red cushion.",
        ("#FBE4E4", "#C3272F"),
        logo_urls=("https://tirtir.global/cdn/shop/files/black.png?v=1763012769&width=600",),
    ),
    BrandSpec(
        "Missha",
        "missha",
        "MSH",
        "The brand behind the original M Perfect Cover BB cream.",
        ("#F4E7E7", "#A33B3B"),
        logo_urls=("https://misshaus.com/cdn/shop/files/Logos_PNG_7.png?v=1760366335&width=600",),
    ),
    BrandSpec(
        "rom&nd",
        "romand",
        "RMD",
        "Colour-led makeup known for its juicy lip tints.",
        ("#F9E8E4", "#C98072"),
        logo_urls=("https://romandbeauty.com/cdn/shop/files/Asset_1.png?width=600",),
    ),
    BrandSpec(
        "Peripera",
        "peripera",
        "PRP",
        "Vivid, long-wearing lip and eye colour.",
        ("#FDE6F0", "#E0307A"),
        logo_urls=("https://theperipera.com/images/logo.png",),
    ),
    BrandSpec(
        "Mise en Scène",
        "mise-en-scene",
        "MES",
        "Hair care and styling, known for the Perfect Serum.",
        ("#FBEFE0", "#D68A2E"),
        logo_urls=(
            "https://www.miseenscene.com/web/upload/category/logo/v2_0e5badcf6af3b91e6ef38d24b2298154_zOeItMbSV2_top.jpg",
        ),
    ),
    BrandSpec(
        "Lador",
        "lador",
        "LDR",
        "Salon-grade hair treatments and scalp care.",
        ("#F3EEE8", "#7A6A58"),
        logo_urls=("https://lador.us/cdn/shop/files/LADOR_logo_black.png?v=1756799884&width=500",),
    ),
    BrandSpec(
        "Aromatica",
        "aromatica",
        "ARM",
        "Vegan skin, hair and body care with essential oils.",
        ("#EBF2EA", "#3F7A4A"),
        logo_urls=("https://www.aromatica.co.kr/layout/basic/img/logotype_b_new.png",),
    ),
    BrandSpec(
        "Nonfiction",
        "nonfiction",
        "NFC",
        "Seoul fragrance house for perfume, body and hand care.",
        ("#F2EFEA", "#8C8274"),
        logo_urls=(
            "https://nonfiction.com/cdn/shop/files/Nonfiction_Logo.png?v=1754783710&width=479",
        ),
    ),
    BrandSpec(
        "Kundal",
        "kundal",
        "KDL",
        "Hair and body care with honey and macadamia.",
        ("#FBF0DD", "#C8872F"),
        logo_urls=(
            "https://www.kundal.co.kr/web/upload/share-image-1-993fc60bea72ef5d1b9759678bbe5cee.jpg",
        ),
    ),
    BrandSpec(
        "Kahi",
        "kahi",
        "KAH",
        "Multi-balm sticks with salmon collagen.",
        ("#FBEDEF", "#C97D8A"),
        logo_urls=("https://www.kahi.co.kr/web/upload/logo/kahi_logo.png",),
    ),
    BrandSpec(
        "Nature Republic",
        "nature-republic",
        "NTR",
        "Nature-led skincare, known for its aloe vera gel.",
        ("#E8F4E4", "#5A9A45"),
        logo_urls=(
            "https://cdn.shopify.com/s/files/1/1740/1531/files/NEW_LOGO-removebg-preview.png?height=628&pad_color=fff&v=1695326317&width=1200",
        ),
    ),
)

SIZES: tuple[tuple[str, str], ...] = (
    ("4 g", "4-g"),
    ("5.5 g", "5-5-g"),
    ("7 g", "7-g"),
    ("9 g", "9-g"),
    ("10 g", "10-g"),
    ("10 ml", "10-ml"),
    ("18 g", "18-g"),
    ("20 g", "20-g"),
    ("30 ml", "30-ml"),
    ("40 ml", "40-ml"),
    ("50 ml", "50-ml"),
    ("55 ml", "55-ml"),
    ("60 ml", "60-ml"),
    ("70 ml", "70-ml"),
    ("80 ml", "80-ml"),
    ("100 ml", "100-ml"),
    ("150 ml", "150-ml"),
    ("180 ml", "180-ml"),
    ("200 ml", "200-ml"),
    ("230 ml", "230-ml"),
    ("250 ml", "250-ml"),
    ("300 ml", "300-ml"),
    ("350 ml", "350-ml"),
    ("500 ml", "500-ml"),
    ("530 ml", "530-ml"),
    ("One size", "one-size"),
)

SHADES: tuple[tuple[str, str, str], ...] = (
    ("17C Porcelain", "tirtir-17c-porcelain", "#F1D6C4"),
    ("21N Ivory", "tirtir-21n-ivory", "#EACBB0"),
    ("21W Natural Ivory", "tirtir-21w-natural-ivory", "#E8C6A4"),
    ("23N Sand", "tirtir-23n-sand", "#DDB592"),
    ("25N Mocha", "tirtir-25n-mocha", "#C99E7A"),
    ("27N Camel", "tirtir-27n-camel", "#B98A64"),
    ("#13 Bright Beige", "missha-13-bright-beige", "#F0D5BF"),
    ("#21 Light Beige", "missha-21-light-beige", "#E8C7A9"),
    ("#23 Natural Beige", "missha-23-natural-beige", "#DDB794"),
    ("#25 Warm Beige", "missha-25-warm-beige", "#D2A882"),
    ("#27 Honey Beige", "missha-27-honey-beige", "#C4966E"),
    ("W01 Odi Milk", "romand-w01-odi-milk", "#EFC3BC"),
    ("W02 Strawberry Milk", "romand-w02-strawberry-milk", "#EDAFB4"),
    ("C01 Peach Chip", "romand-c01-peach-chip", "#EFA98F"),
    ("C03 Fig Chip", "romand-c03-fig-chip", "#C9837F"),
    ("#01 Pure Ivory", "peripera-01-pure-ivory", "#F0D8C0"),
    ("#02 Natural Beige", "peripera-02-natural-beige", "#E3C09E"),
    ("#03 Classic Sand", "peripera-03-classic-sand", "#D3AB85"),
    ("L01 Long Black", "romand-l01-long-black", "#1C1C1C"),
    ("L02 Long Ash", "romand-l02-long-ash", "#5B5550"),
    ("L03 Long Hazel", "romand-l03-long-hazel", "#6B4A36"),
    ("01 Dark Brown", "etude-01-dark-brown", "#4A3326"),
    ("02 Gray Brown", "etude-02-gray-brown", "#6B5D52"),
    ("03 Brown", "etude-03-brown", "#7A553B"),
    ("#05 Peach Me", "romand-05-peach-me", "#F08A6E"),
    ("#06 Fig Fig", "romand-06-fig-fig", "#B8574F"),
    ("#07 Jujube", "romand-07-jujube", "#B3303A"),
    ("#09 Litchi Coral", "romand-09-litchi-coral", "#F07A70"),
    ("#10 Nudy Peanut", "romand-10-nudy-peanut", "#C47F68"),
    ("#12 Cherry Bomb", "romand-12-cherry-bomb", "#B01E3A"),
    ("#01 Good Brick", "peripera-01-good-brick", "#A8453A"),
    ("#02 Celeb Deep Rose", "peripera-02-celeb-deep-rose", "#A94A5A"),
    ("#03 Red Only", "peripera-03-red-only", "#C0232F"),
    ("#04 Lity Coral", "peripera-04-lity-coral", "#E4675A"),
    ("#05 Coralfical", "peripera-05-coralfical", "#E56F63"),
    ("Berry (Pink Tint)", "laneige-berry-pink-tint", "#E68AA0"),
    ("Grapefruit (Coral Tint)", "laneige-grapefruit-coral-tint", "#F29A83"),
    ("Mango (Yellow Tint)", "laneige-mango-yellow-tint", "#F4C95D"),
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

# The invented brands and products an earlier version of this seed created. `--flush`
# removes them, and a retired brand once no product refers to it.
RETIRED_BRAND_SLUGS: tuple[str, ...] = (
    "lumiere",
    "verde-botanics",
    "kaya-rose",
    "nordic-dew",
    "saffron-co",
    "aurum",
    "mistral",
    "bloom-theory",
)
RETIRED_PRODUCT_SLUGS: tuple[str, ...] = (
    "green-tea-gel-cleanser",
    "rose-milk-cleanser",
    "glacier-clay-cleanser",
    "micellar-cleansing-water",
    "papaya-enzyme-polish",
    "glycolic-resurfacing-pads",
    "24k-radiance-serum",
    "hyaluronic-hydra-serum",
    "niacinamide-10-serum",
    "saffron-glow-oil",
    "witch-hazel-balancing-toner",
    "rose-water-toner",
    "rosehip-night-cream",
    "arctic-water-cream",
    "peptide-barrier-cream",
    "caffeine-eye-cream",
    "beeswax-lip-balm",
    "daily-veil-spf-50",
    "mineral-shield-spf-30",
    "silk-foundation",
    "second-skin-concealer",
    "cloud-blush",
    "golden-hour-highlighter",
    "featherlight-mascara",
    "precision-brow-pencil",
    "kohl-kajal",
    "desert-dusk-eyeshadow-palette",
    "velvet-matte-lipstick",
    "satin-lip-crayon",
    "glass-lip-oil",
    "amla-bhringraj-hair-oil",
    "argan-repair-shampoo",
    "silk-protein-conditioner",
    "oud-noir-eau-de-parfum",
    "sea-salt-neroli-eau-de-toilette",
    "damask-rose-eau-de-parfum",
    "lavender-essential-oil",
    "himalayan-cedarwood-oil",
    "shea-body-butter",
    "ubtan-body-scrub",
    "birch-body-wash",
    "oat-milk-bath-soak",
    "arnica-muscle-balm",
    "calendula-rescue-balm",
    "rose-hand-cream",
    "peppermint-foot-cream",
    "sheer-body-sunscreen-spf-50",
    "after-sun-aloe-gel",
)

# Real Korean products. Names, sizes and shades follow the brands' and retailers'
# listings; prices are approximate Nepal retail in NPR. The photos are the brands'
# own, served from their stores or from K-beauty retailers, so they suit a demo only.
#
# Deliberately uneven, so the storefront meets the awkward shapes a merchant can
# produce: a product with no image, one that is sold out, one unpublished, several
# with a price_override on the larger size, and variants at or under the low-stock
# threshold for the admin dashboard.
PRODUCTS: tuple[ProductSpec, ...] = (
    ProductSpec(
        "1025 Dokdo Cleanser",
        "round-lab-1025-dokdo-cleanser",
        "round-lab",
        "cleanse",
        Decimal("1950.00"),
        (
            "A mildly acidic gel-foam cleanser with deep sea water from Ulleungdo. Cleans "
            "without the tight feel."
        ),
        sized(("150-ml", 26)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0249/1218/files/Soko-Glam-Round-Lab-1025-DOKDO-Cleanser.jpg?v=1752798248&width=1000",
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/products/round-lab-1025-dokdo-cleanser-150ml-14164636663874_1024x1024_283d8d4b-80fe-4ffa-bb82-68559d7e3a31.jpg?v=1610676024&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0249/1218/files/Soko-Glam-PDP-Round-Lab-1025-DOKDO-Cleanser-01.png?v=1752771230&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "oily",
            "combination",
            "sensitive",
        ),
        skin_feel="Clean, soft, never stripped",
        key_ingredients="Water (Aqua), Glycerin, Myristic Acid, Sea Water, Panthenol, Allantoin",
    ),
    ProductSpec(
        "Low pH Good Morning Gel Cleanser",
        "cosrx-low-ph-good-morning-gel-cleanser",
        "cosrx",
        "cleanse",
        Decimal("1600.00"),
        "A low-pH gel cleanser with tea tree oil and BHA for a gentle morning wash.",
        sized(("150-ml", 32)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0513/3775/6828/files/low-ph-good-morning-gel-cleanser-cosrx-official-1.jpg?v=1768785801&width=1000",
                "https://cdn.shopify.com/s/files/1/0249/1218/files/COSRX-Low-pH-Good-Morning-Gel-Cleanser-Korean-Skincare-Product.jpg?v=1756221394&width=1000",
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/products/COSRX_Low_pH_Good_Morning_Gel_Cleanser_150ml.png?v=1782406198&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0249/1218/products/2.7-Soko-Glam-PDP-Image-COSRX-Low-pH-Good-Morning-Gel-Cleanser-Korean-Skincare-Product-Lifestyle_1.jpg?v=1753734349&width=1000",
                "https://cdn.shopify.com/s/files/1/0249/1218/products/2.7-Soko-Glam-PDP-Image-COSRX-Low-pH-Good-Morning-Gel-Cleanser-Korean-Skincare-Lifestyle_1.jpg?v=1753734349&width=1000",
            ),
        ),
        skin_types=(
            "oily",
            "combination",
            "normal",
        ),
        skin_feel="Fresh, balanced, comfortable",
        key_ingredients=(
            "Water (Aqua), Cocamidopropyl Betaine, Betaine Salicylate, Melaleuca Alternifolia "
            "(Tea Tree) Leaf Oil, Saccharomyces Ferment"
        ),
    ),
    ProductSpec(
        "Heartleaf Pore Control Cleansing Oil",
        "anua-heartleaf-pore-control-cleansing-oil",
        "anua",
        "cleanse",
        Decimal("3200.00"),
        (
            "A light cleansing oil with heartleaf extract that melts sunscreen and makeup, then "
            "rinses clean."
        ),
        sized(("200-ml", 18)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0753/1429/9158/files/anua-us-cleanser-heartleaf-pore-control-cleansing-oil-1239193742.jpg?v=1779181871&width=1000",
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/AnuaHeartleafPoreControlCleansingOil_Canada_THEKSHOP.webp?v=1690859893&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0753/1429/9158/files/anua-us-cleanser-heartleaf-pore-control-cleansing-oil-1244398150.jpg?v=1781507170&width=1000",
            ),
        ),
        skin_types=(
            "oily",
            "combination",
            "sensitive",
        ),
        skin_feel="Light, clean, residue-free",
        key_ingredients=(
            "Ethylhexyl Palmitate, Caprylic/Capric Triglyceride, Sorbeth-30 Tetraoleate, "
            "Houttuynia Cordata Extract, Glycine Soja (Soybean) Oil"
        ),
    ),
    ProductSpec(
        "Clean It Zero Cleansing Balm Original",
        "banila-co-clean-it-zero-cleansing-balm-original",
        "banila-co",
        "cleanse",
        Decimal("2900.00"),
        "The sherbet-textured balm that turns to oil on contact and lifts even waterproof makeup.",
        sized(("100-ml", 21), ("180-ml", 9, "3950.00")),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0266/0158/6797/files/180ml01.jpg?v=1775637077&width=1000",
                "https://cdn.shopify.com/s/files/1/0249/1218/files/Banila-Co-Cleaning-It-Zero-Original-Cleansing-Balm_2.jpg?v=1756219666&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0266/0158/6797/files/01_89190a21-8ff5-41f9-a3ae-c93721dee6a3.jpg?v=1789111978&width=1000",
                "https://cdn.shopify.com/s/files/1/0249/1218/files/Banila_Co_Clean_It_Zero_Cleansing_Balm_Original_JUMBO_PDP_low.jpg?v=1756218801&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "dry",
            "combination",
        ),
        skin_feel="Silky, clean, supple",
        key_ingredients=(
            "Ethylhexyl Palmitate, Cetyl Ethylhexanoate, PEG-20 Glyceryl Triisostearate, Carica "
            "Papaya (Papaya) Fruit Extract, Malpighia Glabra (Acerola) Fruit Extract"
        ),
    ),
    ProductSpec(
        "BHA Blackhead Power Liquid",
        "cosrx-bha-blackhead-power-liquid",
        "cosrx",
        "exfoliate",
        Decimal("3300.00"),
        "A leave-on 4% betaine salicylate exfoliant for blackheads and congested pores.",
        sized(("100-ml", 15)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0513/3775/6828/files/bha-blackhead-power-liquid-cosrx-official-1.jpg?v=1689840681&width=1000",
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/COSRX_BHA_Blackhead_Power_Liquid_100ml_THEKSHOP_Canada.jpg?v=1782407605&width=1000",
                "https://cdn.shopify.com/s/files/1/0249/1218/files/COSRX-BHA-Blackhead-Power-Liquid-Korean-Skincare-Product.jpg?v=1753399807&width=1000",
            ),
        ),
        skin_types=(
            "oily",
            "combination",
        ),
        skin_feel="Smooth, clear, refined",
        key_ingredients=(
            "Salix Alba (Willow) Bark Water, Butylene Glycol, Betaine Salicylate, Niacinamide, "
            "1,2-Hexanediol"
        ),
    ),
    ProductSpec(
        "Chestnut AHA 8% Clear Essence",
        "isntree-chestnut-aha-8-clear-essence",
        "isntree",
        "exfoliate",
        Decimal("2700.00"),
        "Glycolic and lactic acids with chestnut shell extract to smooth rough texture.",
        sized(("100-ml", 12)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/products/isntree-chestnut-aha-8-clear-essence-main-oo35mm_1024x1024_23712818-4e82-4f99-9faf-090471252522.jpg?v=1665093459&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "oily",
            "combination",
        ),
        skin_feel="Smooth, bright, renewed",
        key_ingredients=(
            "Water (Aqua), Glycolic Acid, Lactic Acid, Castanea Crenata (Chestnut) Shell "
            "Extract, Centella Asiatica Extract"
        ),
    ),
    ProductSpec(
        "Advanced Snail 96 Mucin Power Essence",
        "cosrx-advanced-snail-96-mucin-power-essence",
        "cosrx",
        "treat-masque",
        Decimal("3200.00"),
        "96% snail secretion filtrate in a lightweight essence that hydrates and soothes.",
        sized(("100-ml", 28)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0513/3775/6828/files/james_800x1067_1_1_4e9750cc-2cd6-4817-ace5-be2305a85806.jpg?v=1763111577&width=1000",
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/COSRXAdvancedSnail96MucinPowerEssence_100mL_THEKSHOP_Canada.jpg?v=1782409885&width=1000",
                "https://cdn.shopify.com/s/files/1/0249/1218/files/COSRX-Advanced-Snail-96-Mucin-Power-Essence-Product.jpg?v=1753227743&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0249/1218/products/1.31-Soko-Glam-PDP-Image-COSRX-Advanced-Snail-96-Mucin-Power-Essence-Product-Lifestyle.jpg?v=1753222816&width=1000",
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/COSRXAdvancedSnail96MucinPowerEssence_100mL_THEKSHOP_Canada.jpg?v=1782409885&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "dry",
            "sensitive",
            "mature",
        ),
        skin_feel="Plump, dewy, calm",
        key_ingredients=(
            "Snail Secretion Filtrate, Betaine, Butylene Glycol, Sodium Hyaluronate, Panthenol, "
            "Allantoin"
        ),
    ),
    ProductSpec(
        "Glow Serum: Propolis + Niacinamide",
        "beauty-of-joseon-glow-serum-propolis-niacinamide",
        "beauty-of-joseon",
        "treat-masque",
        Decimal("2100.00"),
        "Propolis and niacinamide in a honey-textured serum for a calm, even glow.",
        sized(("30-ml", 24), ("60-ml", 8, "3300.00")),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0558/4135/7989/files/glow-serum-propolis-niacinamide-1-front.webp?v=1770278801&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0558/4135/7989/files/glow-serum-propolis-niacinamide-7.webp?v=1770278895&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "oily",
            "combination",
        ),
        skin_feel="Glowing, soothed, balanced",
        key_ingredients=(
            "Propolis Extract, Glycerin, Butylene Glycol, Niacinamide, Melaleuca Alternifolia "
            "(Tea Tree) Leaf Extract"
        ),
    ),
    ProductSpec(
        "Madagascar Centella Ampoule",
        "skin1004-madagascar-centella-ampoule",
        "skin1004",
        "treat-masque",
        Decimal("2200.00"),
        "A one-ingredient ampoule of centella asiatica extract from Madagascar for reactive skin.",
        sized(("55-ml", 20), ("100-ml", 7, "3300.00")),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/products/SKIN1004MadagascarCentellaAmpoule100ml.jpg?v=1597452945&width=1000",
                "https://cdn.shopify.com/s/files/1/0590/4538/0253/files/skin1004-ampoule-serum-30ml-centella-ampoule-40725717254390.png?v=1717577033&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0590/4538/0253/products/skin1004-ampoule-serum-centella-ampoule-38409088401654.jpg?v=1677148618&width=1000",
                "https://cdn.shopify.com/s/files/1/0590/4538/0253/products/skin1004-ampoule-serum-madagascar-centella-ampoule-36426919379190.png?v=1677148618&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "oily",
            "combination",
            "sensitive",
        ),
        skin_feel="Calm, light, hydrated",
        key_ingredients="Centella Asiatica Extract",
    ),
    ProductSpec(
        "Water Sleeping Mask",
        "laneige-water-sleeping-mask",
        "laneige",
        "treat-masque",
        Decimal("4600.00"),
        "An overnight gel mask that locks in moisture while you sleep.",
        sized(("70-ml", 14)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0255/0189/2660/files/WSM_AD_PDP_2.jpg?v=1754046790&width=1000",
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/products/6bcd1192-583c-4bf6-97a8-5db4d4c6990f.png?v=1599532677&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0255/0189/2660/files/2895241-av-05.png?v=1775588148&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "dry",
            "combination",
        ),
        skin_feel="Rested, bouncy, hydrated",
        key_ingredients=(
            "Water (Aqua), Butylene Glycol, Glycerin, Trehalose, Hydrolyzed Hyaluronic Acid, "
            "Squalane"
        ),
    ),
    ProductSpec(
        "First Care Activating Serum VI",
        "sulwhasoo-first-care-activating-serum",
        "sulwhasoo",
        "treat-masque",
        Decimal("14500.00"),
        "The ginseng-led first step of a Sulwhasoo routine. Sold out until the next shipment.",
        sized(("60-ml", 0)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0249/8399/4413/files/2023FCAS6thGeneration-60ml-1_270320590_Brand.com_1080px1_1ratio.jpg?v=1732034287&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0249/8399/4413/files/05.FCASRe-PushThumbnailRefresh_SALESDATA__Brand.com_1080px1_1ratio.jpg?v=1773947621&width=1000",
            ),
        ),
        skin_types=(
            "dry",
            "mature",
            "normal",
        ),
        skin_feel="Nourished, supple, radiant",
        key_ingredients=(
            "Water (Aqua), Glycerin, Paeonia Albiflora Root Extract, Lilium Tigrinum Extract, "
            "Rehmannia Glutinosa Root Extract, Nelumbo Nucifera Flower Extract"
        ),
    ),
    ProductSpec(
        "Heartleaf 77% Soothing Toner",
        "anua-heartleaf-77-soothing-toner",
        "anua",
        "tone",
        Decimal("3000.00"),
        "77% heartleaf extract in a watery toner that takes down redness.",
        sized(("250-ml", 25), ("500-ml", 6, "4600.00")),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0753/1429/9158/files/anua-us-toner-heartleaf-77-soothing-toner-1239193744.jpg?v=1779181932&width=1000",
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/AnuaHeartleaf77_SoothingToner.jpg?v=1686877588&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0753/1429/9158/files/anua-us-toner-heartleaf-77-soothing-toner-1161173061.jpg?v=1746609343&width=1000",
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/Anua_Heartleaf_77_Soothing_Toner_New_Packaging.webp?v=1789597628&width=1000",
            ),
        ),
        skin_types=(
            "sensitive",
            "oily",
            "combination",
        ),
        skin_feel="Soothed, fresh, balanced",
        key_ingredients=(
            "Houttuynia Cordata Extract, Water (Aqua), 1,2-Hexanediol, Glycerin, Betaine, Panthenol"
        ),
    ),
    ProductSpec(
        "1025 Dokdo Toner",
        "round-lab-1025-dokdo-toner",
        "round-lab",
        "tone",
        Decimal("2500.00"),
        "A mild exfoliating toner with Ulleungdo deep sea water and panthenol.",
        sized(("200-ml", 19)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0249/1218/files/Round-Lab-1025-DOKDO-Toner.jpg?v=1756219846&width=1000",
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/ROUNDLAB1025DokdoToner.jpg?v=1690491483&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0249/1218/files/Soko-Glam-PDP-Round-Lab-1025-DOKDO-Toner-02.png?v=1754613697&width=1000",
                "https://cdn.shopify.com/s/files/1/0249/1218/files/Soko-Glam-PDP-Round-Lab-1025-DOKDO-Toner-04.png?v=1754613697&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "dry",
            "combination",
            "sensitive",
        ),
        skin_feel="Hydrated, clean, calm",
        key_ingredients="Water (Aqua), Butylene Glycol, Glycerin, Sea Water, Panthenol, Betaine",
    ),
    ProductSpec(
        "AHA-BHA-PHA 30 Days Miracle Toner",
        "some-by-mi-aha-bha-pha-30-days-miracle-toner",
        "some-by-mi",
        "tone",
        Decimal("2300.00"),
        "A tea tree toner with three acids for breakout-prone skin.",
        sized(("150-ml", 17)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0249/1218/files/Soko-Glam-PDP-Some-By-Mi-AHA-BHA-PHA-30-Days-Miracle-Toner-01_924f3d5f-25fd-44e5-a036-cefd2864337b.png?v=1756419421&width=1000",
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/SOMEBYMIAHA_BHA_PHA30DaysMiracleToner_Canada.jpg?v=1696616330&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0249/1218/files/Soko-Glam-PDP-Some-By-Mi-AHA-BHA-PHA-30-Days-Miracle-Toner-04_d667d901-4c51-4ead-804e-b288d84cf8a0.png?v=1756419429&width=1000",
            ),
        ),
        skin_types=(
            "oily",
            "combination",
        ),
        skin_feel="Clear, refreshed, shine-free",
        key_ingredients=(
            "Melaleuca Alternifolia (Tea Tree) Leaf Water, Butylene Glycol, Niacinamide, "
            "Glycolic Acid, Betaine Salicylate, Gluconolactone"
        ),
    ),
    ProductSpec(
        "Water Bank Blue Hyaluronic Cream",
        "laneige-water-bank-blue-hyaluronic-cream",
        "laneige",
        "hydrate",
        Decimal("5600.00"),
        "A lightweight moisturiser with blue hyaluronic acid for all-day hydration.",
        sized(("50-ml", 11)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0255/0189/2660/files/LN_WBCM_24AD_Product_02.jpg?v=1703778486&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "dry",
            "combination",
        ),
        skin_feel="Quenched, supple, dewy",
        key_ingredients=(
            "Water (Aqua), Glycerin, Dipropylene Glycol, Squalane, Hydrolyzed Hyaluronic Acid, "
            "Sodium Hyaluronate"
        ),
    ),
    ProductSpec(
        "Ceramide Ato Concentrate Cream",
        "illiyoon-ceramide-ato-concentrate-cream",
        "illiyoon",
        "hydrate",
        Decimal("3600.00"),
        "A hypoallergenic ceramide cream for face and body, made for dry and sensitive skin.",
        sized(("230-ml", 16)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/IlliyoonCeramideAtoConcentrateCream_Canada.jpg?v=1696119790&width=1000",
            ),
        ),
        skin_types=(
            "dry",
            "sensitive",
        ),
        skin_feel="Rich, comforted, protected",
        key_ingredients=(
            "Water (Aqua), Glycerin, Caprylic/Capric Triglyceride, Ceramide NP, Butyrospermum "
            "Parkii (Shea) Butter"
        ),
    ),
    ProductSpec(
        "DIVE-IN Low Molecular Hyaluronic Acid Soothing Cream",
        "torriden-dive-in-soothing-cream",
        "torriden",
        "hydrate",
        Decimal("3500.00"),
        "Five weights of hyaluronic acid in a light cream that sinks in fast.",
        sized(("100-ml", 13)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0249/1218/files/Soko-Glam-Torriden-Dive-in-Soothing-Cream.jpg?v=1752798489&width=1000",
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/TorridenDIVE-INLowMolecularHyaluronicAcidCream.jpg?v=1694107009&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0249/1218/files/Soko-Glam-PDP-Torriden-Dive-in-Soothing-Cream-05.png?v=1752771530&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "oily",
            "combination",
            "sensitive",
        ),
        skin_feel="Light, cool, hydrated",
        key_ingredients=(
            "Water (Aqua), Butylene Glycol, Glycerin, Sodium Hyaluronate, Hydrolyzed Hyaluronic "
            "Acid, Panthenol, Allantoin"
        ),
    ),
    ProductSpec(
        "SoonJung 2x Barrier Intensive Cream",
        "etude-soonjung-2x-barrier-intensive-cream",
        "etude",
        "hydrate",
        Decimal("2700.00"),
        "Not in the shop yet. If this appears in the public API, visibility scoping is broken.",
        sized(("60-ml", 20)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0249/1218/files/Etude_Revamped_Soonjung_2x_Barrier_Intensive_Cream.jpg?v=1756220690&width=1000",
                "https://cdn.shopify.com/s/files/1/0980/9700/files/Etude_Soonjung_2x_Barrier_Intensive_Cream.jpg?v=1758231018&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0249/1218/files/Soonjung_2xbarrier_Resized.jpg?v=1758827891&width=1000",
                "https://cdn.shopify.com/s/files/1/0980/9700/products/White-Cream-Texture.jpg?v=1758231018&width=1000",
            ),
        ),
        is_published=False,
        skin_types=(
            "sensitive",
            "dry",
        ),
        skin_feel="Calm, resilient, comfortable",
        key_ingredients=(
            "Water (Aqua), Panthenol, Helianthus Annuus (Sunflower) Seed Oil, Butyrospermum "
            "Parkii (Shea) Butter, Madecassoside"
        ),
    ),
    ProductSpec(
        "Lip Sleeping Mask Berry",
        "laneige-lip-sleeping-mask-berry",
        "laneige",
        "eyes-lips",
        Decimal("3300.00"),
        "The overnight lip mask in its original berry flavour.",
        sized(("20-g", 30)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/products/laneigesleepingmaskberrykoreanskincarekbeautycosmeticscanada.jpg?v=1610571265&width=1000",
                "https://cdn.shopify.com/s/files/1/0255/0189/2660/files/LSM_Berry_Infographic_2000x2000Product1_1.jpg?v=1785772326&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0255/0189/2660/files/LSM_Berry_Infographic_2000x2000Product1_1.jpg?v=1785772326&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "dry",
            "sensitive",
        ),
        skin_feel="Soft, smooth, nourished",
        key_ingredients=(
            "Diisostearyl Malate, Hydrogenated Polyisobutene, Butyrospermum Parkii (Shea) "
            "Butter, Rubus Idaeus (Raspberry) Fruit Extract, Vitamin C"
        ),
    ),
    ProductSpec(
        "Revive Eye Serum: Ginseng + Retinal",
        "beauty-of-joseon-revive-eye-serum-ginseng-retinal",
        "beauty-of-joseon",
        "eyes-lips",
        Decimal("2500.00"),
        "Ginseng and retinal in a light eye serum for fine lines and tired eyes.",
        sized(("30-ml", 4)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0558/4135/7989/files/revive-eye-serum-ginseng-retinal-1-front.webp?v=1770287139&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0558/4135/7989/files/15_0420__50ml__v2_b09abffc-c810-4633-998e-d1ae98c36f9d.jpg?v=1777585458&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "dry",
            "mature",
        ),
        skin_feel="Smooth, firm, rested",
        key_ingredients="Panax Ginseng Root Extract, Water (Aqua), Niacinamide, Retinal, Adenosine",
    ),
    ProductSpec(
        "Relief Sun: Rice + Niacinamide SPF50+",
        "beauty-of-joseon-relief-sun-rice-niacinamide",
        "beauty-of-joseon",
        "sun-care",
        Decimal("2300.00"),
        "A creamy chemical sunscreen with rice extract that wears like a moisturiser.",
        sized(("50-ml", 38)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0558/4135/7989/files/03_0805__-_ROW.jpg?v=1787196277&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0558/4135/7989/files/relief-sunscreen-5.webp?v=1774852091&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "dry",
            "combination",
            "sensitive",
        ),
        skin_feel="Dewy, light, protected",
        key_ingredients=(
            "Water (Aqua), Oryza Sativa (Rice) Extract, Dibutyl Adipate, Diethylamino "
            "Hydroxybenzoyl Hexyl Benzoate, Ethylhexyl Triazine, Niacinamide"
        ),
    ),
    ProductSpec(
        "Birch Juice Moisturizing Sun Cream SPF45",
        "round-lab-birch-juice-moisturizing-sun-cream",
        "round-lab",
        "sun-care",
        Decimal("2600.00"),
        "A hydrating daily sunscreen with birch sap and no white cast.",
        sized(("50-ml", 5)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/ROUNDLABBirchJuiceMoisturizingSunCream.jpg?v=1712332806&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "dry",
            "sensitive",
        ),
        skin_feel="Moist, invisible, protected",
        key_ingredients=(
            "Betula Platyphylla Japonica Juice, Water (Aqua), Ethylhexyl Methoxycinnamate, "
            "Ethylhexyl Salicylate, Niacinamide"
        ),
    ),
    ProductSpec(
        "Hyalu-Cica Water-Fit Sun Serum SPF50+",
        "skin1004-hyalu-cica-water-fit-sun-serum",
        "skin1004",
        "sun-care",
        Decimal("2400.00"),
        "A watery sun serum with hyaluronic acid and centella that layers under makeup.",
        sized(("50-ml", 22)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0590/4538/0253/files/skin1004-sun-hyalu-cica-water-fit-sun-serum-spf50-pa-40739561865462.png?v=1776762422&width=1000",
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/SKIN1004MadagascarCentellaHyalu-CicaWater-FitSunSerum_THEKSHOP_Canada.jpg?v=1711653977&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0590/4538/0253/files/skin1004-sun-hyalu-cica-water-fit-sun-serum-1233347071.jpg?v=1776768853&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "oily",
            "combination",
            "sensitive",
        ),
        skin_feel="Watery, light, matte-dewy",
        key_ingredients=(
            "Water (Aqua), Centella Asiatica Extract, Hydrolyzed Hyaluronic Acid, Ethylhexyl "
            "Methoxycinnamate, Diethylamino Hydroxybenzoyl Hexyl Benzoate"
        ),
    ),
    ProductSpec(
        "Mask Fit Red Cushion",
        "tirtir-mask-fit-red-cushion",
        "tirtir",
        "face",
        Decimal("4200.00"),
        "A long-wear cushion foundation with a satin finish and buildable coverage.",
        shaded(
            "18-g",
            ("tirtir-17c-porcelain", 8),
            ("tirtir-21n-ivory", 14),
            ("tirtir-21w-natural-ivory", 3),
            ("tirtir-23n-sand", 11),
            ("tirtir-25n-mocha", 0),
            ("tirtir-27n-camel", 6),
        ),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/TIRTIRMaskFitRedCushion_THEKSHOP_Canada.jpg?v=1715296004&width=1000",
                "https://cdn.shopify.com/s/files/1/1740/1531/files/image_212.png?v=1722447624&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/TIRTIRMaskFitRedCushion_THEKSHOP_Canada_Swatches.webp?v=1715297632&width=1000",
            ),
        ),
    ),
    ProductSpec(
        "M Perfect Cover BB Cream SPF42",
        "missha-m-perfect-cover-bb-cream",
        "missha",
        "face",
        Decimal("2200.00"),
        "The classic high-coverage BB cream with sun protection.",
        shaded(
            "50-ml",
            ("missha-13-bright-beige", 9),
            ("missha-21-light-beige", 15),
            ("missha-23-natural-beige", 12),
            ("missha-25-warm-beige", 4),
            ("missha-27-honey-beige", 7),
        ),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0526/9559/7243/files/Red13.png?v=1785175963&width=1000",
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/MISSHA_M_Perfect_Cover_BB_Cream-THEKSHOP_Canada.jpg?v=1775263542&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0526/9559/7243/files/US__PDP___BB__50ml_31.jpg?v=1785165875&width=1000",
            ),
        ),
    ),
    ProductSpec(
        "Better Than Cheek",
        "romand-better-than-cheek",
        "romand",
        "face",
        Decimal("1900.00"),
        "A soft powder blush with a milky, diffused finish.",
        shaded(
            "4-g",
            ("romand-w01-odi-milk", 12),
            ("romand-w02-strawberry-milk", 9),
            ("romand-c01-peach-chip", 6),
            ("romand-c03-fig-chip", 3),
        ),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/romand_Better_Than_Cheek_NEW_THEKSHOP_Canada.png?v=1773970374&width=1000",
                "https://cdn.shopify.com/s/files/1/0598/8578/1067/files/W01_ODI_MILK_1.jpg?v=1771982826&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/romand_Better_Than_Cheek_NEW-swtaches.png?v=1773970374&width=1000",
            ),
        ),
    ),
    ProductSpec(
        "Double Longwear Cover Concealer",
        "peripera-double-longwear-cover-concealer",
        "peripera",
        "face",
        Decimal("1700.00"),
        "A creamy, long-wearing concealer for dark circles and blemishes.",
        shaded(
            "5-5-g",
            ("peripera-01-pure-ivory", 10),
            ("peripera-02-natural-beige", 13),
            ("peripera-03-classic-sand", 5),
        ),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/products/periperadoublelongwearcoverconcealer.jpg?v=1643343999&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/products/periperadoublelongwearcoverconcealer_28d47698-8bd6-42c0-9c98-f0b2367d5479.jpg?v=1643343953&width=1000",
            ),
        ),
    ),
    ProductSpec(
        "Han All Fix Mascara",
        "romand-han-all-fix-mascara",
        "romand",
        "eyes",
        Decimal("2300.00"),
        "A fine-brush mascara that lengthens and holds a curl all day.",
        shaded(
            "7-g",
            ("romand-l01-long-black", 18),
            ("romand-l02-long-ash", 7),
            ("romand-l03-long-hazel", 5),
        ),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/products/romandhanallfixmascara.jpg?v=1651593051&width=1000",
                "https://cdn.shopify.com/s/files/1/0598/8578/1067/files/UHMC02_VOLUME_BLACK_1.jpg?v=1770108459&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/products/romandhanallfixmascara.png?v=1651593051&width=1000",
            ),
        ),
    ),
    ProductSpec(
        "Drawing Eye Brow",
        "etude-drawing-eye-brow",
        "etude",
        "eyes",
        Decimal("850.00"),
        "A twist-up brow pencil with a flat tip for natural strokes, spoolie included.",
        shaded(
            "one-size",
            ("etude-01-dark-brown", 24),
            ("etude-02-gray-brown", 19),
            ("etude-03-brown", 11),
        ),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/EtudeHouseDrawingEyeBrow_THEKSHOP_Canada.jpg?v=1712959002&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/EtudeDrawingEyeBrow_THEKSHOP_Canada.jpg?v=1712958999&width=1000",
            ),
        ),
    ),
    ProductSpec(
        "Ink Pocket Shadow Palette #06 Welcoming Woody Home",
        "peripera-ink-pocket-shadow-palette-welcoming-woody-home",
        "peripera",
        "eyes",
        Decimal("2900.00"),
        "Four warm brown mattes and shimmers in a pocket-size palette.",
        sized(("one-size", 4)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/products/PeriperaInkPocketShadowPalette_WelcomingWoodyHome.png?v=1727980257&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/products/PeriperaInkPocketShadowPalette_WelcomingWoodyHome.jpg?v=1634661324&width=1000",
            ),
        ),
    ),
    ProductSpec(
        "Juicy Lasting Tint",
        "romand-juicy-lasting-tint",
        "romand",
        "lips",
        Decimal("1900.00"),
        "The glossy, long-lasting lip tint that set off rom&nd's cult following.",
        shaded(
            "5-5-g",
            ("romand-05-peach-me", 16),
            ("romand-06-fig-fig", 22),
            ("romand-07-jujube", 14),
            ("romand-09-litchi-coral", 5),
            ("romand-10-nudy-peanut", 9),
            ("romand-12-cherry-bomb", 7),
        ),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/products/rom_nd_JUICYLASTINGTINT_THEKSHOP_Canada_KBeauty.jpg?v=1632360170&width=1000",
                "https://cdn.shopify.com/s/files/1/0598/8578/1067/files/07_JUJUBE_1.jpg?v=1775131605&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/products/01_juicy-oh__rom_nd_JUICYLASTINGTINT_THEKSHOP_Canada_KBeauty.jpg?v=1632360183&width=1000",
            ),
        ),
    ),
    ProductSpec(
        "Ink The Velvet",
        "peripera-ink-the-velvet",
        "peripera",
        "lips",
        Decimal("1800.00"),
        "A lightweight velvet lip tint with a blurred, soft-matte finish.",
        shaded(
            "4-g",
            ("peripera-01-good-brick", 13),
            ("peripera-02-celeb-deep-rose", 8),
            ("peripera-03-red-only", 11),
            ("peripera-04-lity-coral", 2),
            ("peripera-05-coralfical", 6),
        ),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/products/PeriperaInktheVelvet_AD.jpg?v=1668921225&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/products/PeriperaInktheVelvet_AD__colorchart.jpg?v=1668921234&width=1000",
            ),
        ),
    ),
    ProductSpec(
        "Lip Glowy Balm",
        "laneige-lip-glowy-balm",
        "laneige",
        "lips",
        Decimal("2900.00"),
        "A sheer-tinted, glossy lip balm with shea butter for the daytime.",
        shaded(
            "10-g",
            ("laneige-berry-pink-tint", 15),
            ("laneige-grapefruit-coral-tint", 10),
            ("laneige-mango-yellow-tint", 7),
        ),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0255/0189/2660/files/LGB_AMS_Infographic_2000x2000_Product_2_1.jpg?v=1782826928&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0255/0189/2660/files/LGB_Vanilla_Infographic_2000x2000Product2.jpg?v=1785777144&width=1000",
            ),
        ),
    ),
    ProductSpec(
        "Perfect Serum Original",
        "mise-en-scene-perfect-serum-original",
        "mise-en-scene",
        "haircare",
        Decimal("1800.00"),
        "A lightweight hair oil serum with seven oils for frizz and heat damage.",
        sized(("80-ml", 27)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/MiseenScenePerfectSerumOriginal_Canada.jpg?v=1693321383&width=1000",
            ),
        ),
    ),
    ProductSpec(
        "Dermatical Hair-Loss Shampoo",
        "lador-dermatical-hair-loss-shampoo",
        "lador",
        "haircare",
        Decimal("3900.00"),
        "A scalp-care shampoo for thinning hair and a sensitive scalp.",
        sized(("530-ml", 12)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/LADORDermaticalHair-LossShampoo.jpg?v=1694455882&width=1000",
            ),
        ),
    ),
    ProductSpec(
        "Rosemary Scalp Scaling Shampoo",
        "aromatica-rosemary-scalp-scaling-shampoo",
        "aromatica",
        "haircare",
        Decimal("2600.00"),
        "A vegan, sulphate-free shampoo with rosemary for an oily, flaky scalp.",
        sized(("180-ml", 16)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/aromaticarosemaryscalpscalingshampoo180ml_Canada_THEKSHOP.jpg?v=1690860700&width=1000",
            ),
        ),
    ),
    ProductSpec(
        "Gentle Night Eau de Parfum",
        "nonfiction-gentle-night-eau-de-parfum",
        "nonfiction",
        "perfume",
        Decimal("20500.00"),
        "Soft musk, iris and vanilla. Quiet and close to the skin.",
        sized(("50-ml", 7), ("100-ml", 3, "29000.00")),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0086/7116/6511/files/nonfiction-parfum-gentle-night-eau-de-parfum-1204072860.jpg?v=1762743186&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0086/7116/6511/files/nonfiction-parfum-50ml-gentle-night-eau-de-parfum-1194135635.jpg?v=1764922202&width=1000",
            ),
        ),
    ),
    ProductSpec(
        "Santal Cream Eau de Parfum",
        "nonfiction-santal-cream-eau-de-parfum",
        "nonfiction",
        "perfume",
        Decimal("20500.00"),
        "Sandalwood, vetiver, fig and cardamom.",
        sized(("50-ml", 9), ("100-ml", 4, "29000.00")),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0086/7116/6511/files/nonfiction-parfum-50-ml-1-6-fl-oz-santal-cream-eau-de-parfum-1194469979.jpg?v=1758682509&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0086/7116/6511/files/nonfiction-parfum-santal-cream-eau-de-parfum-1198706354.jpg?v=1774486214&width=1000",
            ),
        ),
    ),
    ProductSpec(
        "Forget Me Not Eau de Parfum",
        "nonfiction-forget-me-not-eau-de-parfum",
        "nonfiction",
        "perfume",
        Decimal("20500.00"),
        "Bright bergamot and white flowers over a clean musk base.",
        sized(("50-ml", 6), ("100-ml", 2, "29000.00")),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0086/7116/6511/files/nonfiction-parfum-50ml-forget-me-not-eau-de-parfum-1194135664.jpg?v=1758598271&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0086/7116/6511/files/nonfiction-parfum-100ml-forget-me-not-eau-de-parfum-1194135666.jpg?v=1758788981&width=1000",
            ),
        ),
    ),
    ProductSpec(
        "Lavender Essential Oil",
        "aromatica-lavender-essential-oil",
        "aromatica",
        "essential-oils",
        Decimal("2900.00"),
        "100% pure lavender oil for a bath, a pillow or a diffuser.",
        sized(("10-ml", 21)),
        image_urls=(
            (
                "https://stylejolly.com/storage/bluewhale1015EN/www/prefix/product/2023/47/O/product.2897.170070587610191.jpeg",
                "https://www.cdn3.kr/http://stylejolly.com/storage/bluewhale1015EN/www/prefix/product/2023/47/O/product.2897.170070587610191.jpeg",
            ),
        ),
    ),
    ProductSpec(
        "Rosemary Essential Oil",
        "aromatica-rosemary-essential-oil",
        "aromatica",
        "essential-oils",
        Decimal("2900.00"),
        "100% pure rosemary oil with a fresh, herbal scent.",
        sized(("10-ml", 14)),
        image_urls=(
            (
                "https://stylejolly.com/storage/bluewhale1015EN/www/prefix/product/2023/47/O/product.2898.170070587676412.jpeg",
                "https://www.cdn3.kr/http://stylejolly.com/storage/bluewhale1015EN/www/prefix/product/2023/47/O/product.2898.170070587676412.jpeg",
            ),
        ),
    ),
    ProductSpec(
        "Tea Tree Essential Oil",
        "aromatica-tea-tree-essential-oil",
        "aromatica",
        "essential-oils",
        Decimal("2900.00"),
        "100% pure tea tree oil, sharp and clean.",
        sized(("10-ml", 17)),
        image_urls=(
            (
                "https://stylejolly.com/storage/bluewhale1015EN/www/prefix/product/2023/47/O/product.2899.170070588230701.jpeg",
                "https://www.cdn3.kr/http://stylejolly.com/storage/bluewhale1015EN/www/prefix/product/2023/47/O/product.2899.170070588230701.jpeg",
            ),
        ),
    ),
    ProductSpec(
        "Ceramide Ato Lotion",
        "illiyoon-ceramide-ato-lotion",
        "illiyoon",
        "creams-oils-scrubs",
        Decimal("4000.00"),
        "A fragrance-free ceramide body lotion for very dry skin.",
        sized(("350-ml", 15)),
        # No image at all: the card and the gallery both have to survive it.
        skin_types=(
            "dry",
            "sensitive",
        ),
        skin_feel="Soft, comforted, non-greasy",
        key_ingredients=(
            "Water (Aqua), Glycerin, Caprylic/Capric Triglyceride, Ceramide NP, Cholesterol"
        ),
    ),
    ProductSpec(
        "Exfoliating Body Scrub & Wash",
        "nonfiction-exfoliating-body-scrub-wash",
        "nonfiction",
        "creams-oils-scrubs",
        Decimal("6200.00"),
        "A fine-grain scrub and body wash in one, with a soft woody scent.",
        sized(("200-ml", 8)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0086/7116/6511/files/nonfiction-body-scrub-200ml-exfoliating-body-scrub-wash-1197512261.jpg?v=1760439195&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0086/7116/6511/files/nonfiction-body-scrub-200ml-exfoliating-body-scrub-wash-1197512262.jpg?v=1760439197&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "oily",
            "combination",
        ),
        skin_feel="Polished, smooth, fresh",
        key_ingredients=(
            "Water (Aqua), Sodium Cocoyl Isethionate, Glycerin, Olea Europaea (Olive) Seed "
            "Powder, Panthenol"
        ),
    ),
    ProductSpec(
        "Gentle Night Body Wash",
        "nonfiction-gentle-night-body-wash",
        "nonfiction",
        "shower-bath",
        Decimal("6200.00"),
        "A low-foam body wash in the Gentle Night scent.",
        sized(("300-ml", 10)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0086/7116/6511/files/nonfiction-body-wash-300ml-replacement-push-pump-1-00-gentle-night-body-wash-1194135640.jpg?v=1758597805&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0086/7116/6511/files/nonfiction-body-wash-300ml-replacement-push-pump-1-00-gentle-night-body-wash-1194135639.jpg?v=1758597802&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "dry",
        ),
        skin_feel="Soft, clean, lightly scented",
        key_ingredients=(
            "Water (Aqua), Sodium Lauroyl Methyl Isethionate, Cocamidopropyl Betaine, Glycerin, "
            "Panthenol"
        ),
    ),
    ProductSpec(
        "Honey & Macadamia Body Wash Pink Grapefruit",
        "kundal-honey-macadamia-body-wash-pink-grapefruit",
        "kundal",
        "shower-bath",
        Decimal("2300.00"),
        "A pH-balanced body wash with honey and macadamia oil in a fresh grapefruit scent.",
        sized(("500-ml", 24)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/KUNDAL_Honey_Macadamia_Body_Wash_THEKSHOP_Canada.jpg?v=1749345907&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "dry",
            "oily",
        ),
        skin_feel="Fresh, soft, moisturised",
        key_ingredients=(
            "Water (Aqua), Sodium Laureth Sulfate, Honey Extract, Macadamia Ternifolia Seed "
            "Oil, Glycerin"
        ),
    ),
    ProductSpec(
        "Wrinkle Bounce Multi Balm",
        "kahi-wrinkle-bounce-multi-balm",
        "kahi",
        "balms",
        Decimal("4900.00"),
        "A multi-use balm stick with salmon collagen for face, lips and dry patches.",
        sized(("9-g", 3)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/products/kahiwrinklebouncemultibalm.png?v=1645211352&width=1000",
            ),
        ),
        skin_types=(
            "dry",
            "mature",
        ),
        skin_feel="Dewy, firm, nourished",
        key_ingredients=(
            "Hydrolyzed Collagen, Olea Europaea (Olive) Fruit Oil, Sodium DNA, Squalane, Tocopherol"
        ),
    ),
    ProductSpec(
        "SoonJung Centella 10-Panthensoside Cica Balm",
        "etude-soonjung-centella-cica-balm",
        "etude",
        "balms",
        Decimal("2800.00"),
        "A calming cica balm with panthenol and madecassoside for irritated skin.",
        sized(("40-ml", 14)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/ETUDE_HOUSE_Soon_Jung_Centella_5-Panthensoside_Cica_Balm_THEKSHOP_Canada.webp?v=1721854986&width=1000",
            ),
        ),
        skin_types=(
            "sensitive",
            "dry",
        ),
        skin_feel="Soothed, protected, repaired",
        key_ingredients=(
            "Water (Aqua), Centella Asiatica Leaf Water, Panthenol, Madecassoside, "
            "Butyrospermum Parkii (Shea) Butter"
        ),
    ),
    ProductSpec(
        "Santal Cream Hand Cream",
        "nonfiction-santal-cream-hand-cream",
        "nonfiction",
        "hands-feet",
        Decimal("4000.00"),
        "A fast-absorbing hand cream in the Santal Cream scent.",
        sized(("50-ml", 11)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0086/7116/6511/files/nonfiction-hand-cream-50ml-santal-cream-hand-cream-1194135570.jpg?v=1758596603&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0086/7116/6511/files/nonfiction-hand-cream-50ml-santal-cream-hand-cream-1194135569.jpg?v=1758596599&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "dry",
        ),
        skin_feel="Velvety, soft, non-greasy",
        key_ingredients=(
            "Water (Aqua), Glycerin, Butyrospermum Parkii (Shea) Butter, Squalane, Panthenol"
        ),
    ),
    ProductSpec(
        "Birch Juice Hand Cream",
        "round-lab-birch-juice-hand-cream",
        "round-lab",
        "hands-feet",
        Decimal("950.00"),
        "A light hand cream with birch sap for everyday dryness.",
        sized(("30-ml", 5)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0054/4587/7809/files/ROUND_LA_BBirch_Juice_Hand_Cream_30mL_THEKSHOP_Canada.jpg?v=1790279393&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "dry",
        ),
        skin_feel="Light, moist, fresh",
        key_ingredients=(
            "Betula Platyphylla Japonica Juice, Water (Aqua), Glycerin, Butyrospermum Parkii "
            "(Shea) Butter, Panthenol"
        ),
    ),
    ProductSpec(
        "Hydra Shield Body Sun Lotion SPF50+",
        "beauty-of-joseon-hydra-shield-body-sun-lotion",
        "beauty-of-joseon",
        "sun-protection",
        Decimal("3700.00"),
        "A lightweight body sunscreen that absorbs quickly and leaves no cast.",
        sized(("150-ml", 13)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/0558/4135/7989/files/BOJ260504.jpg?v=1777888935&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/0558/4135/7989/files/BOJ_PLP_1_23d402b1-5a35-47be-8d7d-1bdfea7f90cf.jpg?v=1778479601&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "dry",
            "oily",
        ),
        skin_feel="Light, hydrated, protected",
        key_ingredients=(
            "Water (Aqua), Oryza Sativa (Rice) Extract, Ethylhexyl Triazone, "
            "Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine, Glycerin"
        ),
    ),
    ProductSpec(
        "Mild & Moisture Aloe Vera Watery Gel",
        "nature-republic-aloe-vera-watery-gel",
        "nature-republic",
        "sun-protection",
        Decimal("1150.00"),
        "A 92% aloe gel for after-sun cooling on face and body.",
        sized(("300-ml", 40)),
        image_urls=(
            (
                "https://cdn.shopify.com/s/files/1/1740/1531/files/71G2E7xxVTL._SX679.jpg?v=1773861042&width=1000",
            ),
            (
                "https://cdn.shopify.com/s/files/1/1740/1531/files/71p0Tv1erUL._SX679.jpg?v=1760735836&width=1000",
            ),
        ),
        skin_types=(
            "normal",
            "dry",
            "sensitive",
        ),
        skin_feel="Cool, soothed, hydrated",
        key_ingredients=(
            "Aloe Barbadensis Leaf Extract, Butylene Glycol, Glycerin, Sodium Polyacrylate, "
            "Panthenol"
        ),
    ),
)
