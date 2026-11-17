"""
All the knobs you might want to turn live in this one file.
Change a value, save, and the bot uses it on its next run.
"""
import os

# ---------------------------------------------------------------------------
# Safety switches
# ---------------------------------------------------------------------------
# DRY_RUN = true  -> the bot finds trends, makes designs and sends them to
#                    Telegram, but never creates Etsy listings or Printful
#                    orders. Start here. Flip the GitHub variable DRY_RUN to
#                    "false" when you're happy with what you see.
DRY_RUN = os.getenv("DRY_RUN", "true").lower() != "false"

# Publish approved listings live (True) or leave them as Etsy drafts (False).
PUBLISH_LIVE = os.getenv("PUBLISH_LIVE", "true").lower() != "false"

# Send paid Etsy orders straight to production at Printful (True), or leave
# them as Printful drafts for you to confirm by hand (False).
AUTO_CONFIRM_ORDERS = os.getenv("AUTO_CONFIRM_ORDERS", "true").lower() != "false"

# ---------------------------------------------------------------------------
# How much the bot makes
# ---------------------------------------------------------------------------
# The bot works from 9am to 5pm Eastern, once every 40 minutes (12 runs a day),
# and makes 2 new designs each run (about 24 a day).
WORK_TIMEZONE = "America/New_York"
WORK_START_HOUR = 9     # 9am
WORK_END_HOUR = 17      # 5pm
RUN_EVERY_MINUTES = 40
DESIGNS_PER_BATCH = int(os.getenv("DESIGNS_PER_BATCH", "2"))
ILLUSTRATION_SHARE = 0.30          # 70% text designs, 30% illustrations
MAX_PENDING_APPROVALS = 15         # stop making new designs if this many are waiting on you

# ---------------------------------------------------------------------------
# AI models
# ---------------------------------------------------------------------------
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-2.5-flare")
IMAGE_SIZE = os.getenv("IMAGE_SIZE", "2048x3072")   # largest size within OpenAI's pixel budget; falls back smaller if refused

# ---------------------------------------------------------------------------
# Shop voice. Used in every listing description.
# ---------------------------------------------------------------------------
SHOP_NAME = os.getenv("SHOP_NAME", "our studio")
RETURNS = (
    "\n\nReturns and exchanges\n"
    "Every piece is printed just for you, so we can't accept returns or exchanges for size, color "
    "or a change of mind. Please check the size chart in the photos before ordering.\n"
    "If your order arrives misprinted, damaged or defective, message us within 30 days of delivery "
    "with a photo and we'll send a free replacement or a refund. The same goes if your package is "
    "lost in the mail."
)

DISCLOSURE = (
    "\n\nAbout this item\n"
    "Designed by {shop} with the help of AI design tools, then reviewed and "
    "approved by a real person before listing. Made to order and printed for "
    "you by our production partner, Printful."
)

# ---------------------------------------------------------------------------
# Products. These are Printful's best sellers: tees and hoodies lead, with
# mugs and stickers as low-cost add-ons.
#
# search     words used to find the product in Printful's catalog
# fallback   Printful catalog id to use if the search finds nothing
# placement  where the design prints
# colors     garment colors offered, for designs with dark ink (light) or
#            light ink (dark). None = product only comes in white.
# markup     retail price = Printful cost x markup, never below min_price
# fit        how the design sits in the print area
# ---------------------------------------------------------------------------
PRODUCTS = {
    "tee": {
        "label": "T-Shirt",
        "search": ["bella + canvas 3001", "unisex staple t-shirt"],
        "fallback": 71,
        "placement": "front",
        "sizes": ["S", "M", "L", "XL", "2XL"],
        "colors": {"light": ["White", "Athletic Heather"], "dark": ["Black", "Navy"]},
        "markup": 2.0,
        "min_price": 26.99,
        "fit": "top",
        "max_height": 0.62,      # share of the 16 in print height (about 10 in)
        "scale": 0.90,           # Daniel: tee designs 10% smaller
        "etsy_category": ["t-shirts", "t shirts"],
        "details": "Soft, lightweight unisex tee (Bella+Canvas 3001). 100% combed and "
                   "ring-spun cotton (heather colors are a cotton/poly blend). Runs true to size.",
    },
    "hoodie": {
        "label": "Hoodie",
        "search": ["gildan 18500", "unisex heavy blend hoodie"],
        "fallback": 146,
        "placement": "front",
        "sizes": ["S", "M", "L", "XL", "2XL"],
        "colors": {"light": ["White", "Sport Grey"], "dark": ["Black", "Navy"]},
        "markup": 1.8,
        "min_price": 44.99,
        "fit": "top",
        "max_height": 0.50,      # stay above the front pouch pocket
        "scale": 1.10,           # Daniel: hoodie designs 10% bigger
        "etsy_category": ["hoodies", "sweatshirts"],
        "details": "Cozy unisex hoodie (Gildan 18500). 50% cotton, 50% polyester, "
                   "double-lined hood, front pouch pocket.",
    },
    "mug": {
        "label": "Mug",
        "search": ["white glossy mug"],
        "fallback": 19,
        "placement": "default",
        "sizes": ["11 oz", "15 oz"],
        "colors": None,
        "markup": 2.2,
        "min_price": 17.99,
        "fit": "mug",
        "etsy_category": ["mugs"],
        "details": "Glossy white ceramic mug, printed on both sides. Dishwasher and microwave safe.",
    },
    "sticker": {
        "label": "Sticker",
        "search": [],            # use Printful's standard Kiss-Cut Stickers (#358), not the sticker sheet
        "fallback": 358,
        "placement": "default",
        "sizes": ["3x3", "4x4", "5.5x5.5"],
        "colors": None,
        "markup": 2.2,
        "min_price": 4.99,
        "fit": "center",
        "etsy_category": ["stickers"],
        "details": "Durable vinyl kiss-cut sticker with a glossy finish. Great for laptops, "
                   "water bottles and journals.",
    },
}

# Text design styles the AI picks from: a lead font (main) and an accent font for one line.
# Each has a category (sans, serif, geometric, script, other) so Rory can keep a varied mix.
# Pairings follow common designer advice: one bold lead plus one contrasting accent, same era.
# All fonts are Google Fonts / open-license (SIL OFL); license files are in /fonts.
TEXT_STYLES = {
    # bold and modern
    "streetwear":   {"category": "sans", "main": "anton.woff",              "accent": "montserrat-extrabold.woff",
                     "mood": "loud condensed slogans, streetwear, gym, confident statements"},
    "bold_stack":   {"category": "sans", "main": "bebas-neue.woff",         "accent": "pacifico.woff",
                     "mood": "tall clean caps with a casual script accent; versatile everyday slogans"},
    "heavy_block":  {"category": "sans", "main": "archivo-black.woff",      "accent": "lobster.woff",
                     "mood": "heavy, punchy, sporty; short phrases"},
    "modern_clean": {"category": "geometric", "main": "poppins-extrabold.woff",  "accent": "dm-serif-display-italic.woff",
                     "mood": "friendly modern minimal; wellness, self-care, gentle humor"},
    "modern_bold":  {"category": "sans", "main": "BricolageGrotesque-Bold.ttf", "accent": "permanent-marker.woff",
                     "mood": "quirky contemporary; indie, creative, design-y crowd"},
    "bold_mono":    {"category": "geometric", "main": "rubik-mono-one.woff",     "accent": "poppins-extrabold.woff",
                     "mood": "chunky wide geometric caps; playful, techy, arcade"},
    # sporty and signage
    "athletic":     {"category": "sans", "main": "oswald-bold.woff",        "accent": "pacifico.woff",
                     "mood": "team, club, sports, varsity-feeling slogans"},
    "signage":      {"category": "sans", "main": "staatliches.woff",        "accent": "pacifico.woff",
                     "mood": "compact vintage sign lettering; shops, clubs, places"},
    "tall_poster":  {"category": "sans", "main": "BigShoulders-Bold.ttf",   "accent": "lobster.woff",
                     "mood": "tall industrial poster type; city, work, grit"},
    "chunky_sign":  {"category": "other", "main": "bungee.woff",             "accent": "oswald-bold.woff",
                     "mood": "chunky urban signage; bold, fun, loud"},
    "long_phrase":  {"category": "sans", "main": "fjalla-one.woff",         "accent": "lora-bold-italic.woff",
                     "mood": "condensed type that fits longer lines neatly; quotes and wordier jokes"},
    # retro and vintage
    "seventies":    {"category": "script", "main": "shrikhand.woff",          "accent": "josefin-sans-bold.woff",
                     "mood": "groovy 70s retro, warm and curvy; nostalgia, good vibes"},
    "fifties":      {"category": "geometric", "main": "josefin-sans-bold.woff",  "accent": "lobster.woff",
                     "mood": "50s diner and Americana; script with clean geometric caps"},
    "retro_slab":   {"category": "serif", "main": "alfa-slab-one.woff",      "accent": "pacifico.woff",
                     "mood": "chunky retro slab; vintage sporting goods, Americana"},
    "groovy":       {"category": "geometric", "main": "righteous.woff",          "accent": "pacifico.woff",
                     "mood": "art deco 70s/80s retro; rounded and friendly"},
    "outdoors":     {"category": "serif", "main": "arvo-bold.woff",          "accent": "lobster.woff",
                     "mood": "outdoorsy vintage slab; camping, hiking, cabins, national-park feel"},
    "park_sign":    {"category": "sans", "main": "NationalPark-Bold.ttf",   "accent": "pacifico.woff",
                     "mood": "national park trail-sign lettering; nature, adventure"},
    "western":      {"category": "other", "main": "rye.woff",                "accent": "arvo-bold.woff",
                     "mood": "old west saloon poster; cowboy, ranch, rodeo humor"},
    # elegant and editorial
    "editorial_fat": {"category": "serif", "main": "playfair-black.woff",    "accent": "raleway-extrabold.woff",
                      "mood": "high-contrast fashion serif; chic, literary, elegant statements"},
    "elegant":      {"category": "serif", "main": "abril-fatface.woff",      "accent": "josefin-sans-bold.woff",
                     "mood": "fat-face serif with a clean sans; classy, bookish, bold-elegant"},
    "romantic_serif": {"category": "serif", "main": "dm-serif-display.woff", "accent": "playfair-bold-italic.woff",
                       "mood": "soft romantic serif; love, family, gratitude, gift-y sentiment"},
    "editorial":    {"category": "serif", "main": "Gloock-Regular.ttf",      "accent": "pacifico.woff",
                     "mood": "sharp editorial serif; witty grown-up humor"},
    "warm_serif":   {"category": "serif", "main": "YoungSerif-Regular.ttf",  "accent": "lobster.woff",
                     "mood": "warm friendly serif; cozy, home, coffee, slow living"},
    # playful and hand-made
    "comic":        {"category": "other", "main": "bangers.woff",            "accent": "poppins-extrabold.woff",
                     "mood": "comic book energy; kids, puns, silly humor"},
    "bubbly":       {"category": "other", "main": "titan-one.woff",          "accent": "pacifico.woff",
                     "mood": "round bubbly and cheerful; kids, cute animals, sweet treats"},
    "hand_marker":  {"category": "script", "main": "permanent-marker.woff",   "accent": "montserrat-extrabold.woff",
                     "mood": "handmade marker; DIY, honest, casual quotes"},
    "script_pop":   {"category": "script", "main": "lobster.woff",            "accent": "bebas-neue.woff",
                     "mood": "bold retro script lead; sweet, nostalgic, signature-style"},
    # ---- added for a fuller mix ----
    # script and handwriting leads
    "brush_script":   {"category": "script", "main": "kaushan-script.woff", "accent": "oswald-bold.woff",
                       "mood": "energetic brush script; adventure, travel, surf, outdoors energy"},
    "handwritten":    {"category": "script", "main": "caveat-brush.woff", "accent": "montserrat-extrabold.woff",
                       "mood": "casual handwriting like a personal note; teachers, moms, sweet everyday humor"},
    "elegant_script": {"category": "script", "main": "dancing-script-bold.woff", "accent": "josefin-sans-bold.woff",
                       "mood": "flowing elegant script; love, family, gratitude, celebrations"},
    "retro_script":   {"category": "script", "main": "yellowtail.woff", "accent": "bebas-neue.woff",
                       "mood": "retro signature script; vintage cars, diners, nostalgia"},
    "breezy_script":  {"category": "script", "main": "satisfy.woff", "accent": "montserrat-extrabold.woff",
                       "mood": "light breezy script; beach, summer, slow mornings"},
    # geometric leads
    "geo_black":      {"category": "geometric", "main": "montserrat-black.woff", "accent": "dancing-script-bold.woff",
                       "mood": "clean heavy geometric caps with a flowing script; modern, confident, versatile"},
    "rounded_friendly": {"category": "geometric", "main": "fredoka-bold.woff", "accent": "yellowtail.woff",
                         "mood": "rounded friendly geometric; kids, pets, cheerful and soft"},
    # other: typewriter, blackletter, stencil
    "typewriter":     {"category": "other", "main": "special-elite.woff", "accent": "dancing-script-bold.woff",
                       "mood": "vintage typewriter; bookish, writers, dry literary humor"},
    "blackletter":    {"category": "other", "main": "unifraktur.woff", "accent": "montserrat-black.woff",
                       "mood": "gothic blackletter; streetwear edge, old-world, tongue-in-cheek drama"},
    "stencil":        {"category": "other", "main": "black-ops-one.woff", "accent": "oswald-bold.woff",
                       "mood": "military stencil; rugged, workwear, utility, dad humor"},
}

# News and trend feeds the scout reads.
FEEDS = [
    "https://trends.google.com/trending/rss?geo=US",
    "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=viral+trend&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=new+hobby+trend&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=gen+z+trend&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=wellness+trend&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=pets+trend&hl=en-US&gl=US&ceid=US:en",
]
