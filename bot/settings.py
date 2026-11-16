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
IMAGE_SIZE = os.getenv("IMAGE_SIZE", "2560x3840")   # falls back to 1024x1536 if refused

# ---------------------------------------------------------------------------
# Shop voice. Used in every listing description.
# ---------------------------------------------------------------------------
SHOP_NAME = os.getenv("SHOP_NAME", "our studio")
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

# Text design styles the AI picks from (main font, accent font). All fonts are open-license.
TEXT_STYLES = {
    "bold_stack":   {"main": "bebas-neue.woff",       "accent": "pacifico.woff"},
    "heavy_block":  {"main": "archivo-black.woff",    "accent": "lobster.woff"},
    "retro_slab":   {"main": "alfa-slab-one.woff",    "accent": "pacifico.woff"},
    "elegant":      {"main": "abril-fatface.woff",    "accent": "lobster.woff"},
    "hand_marker":  {"main": "permanent-marker.woff", "accent": "permanent-marker.woff"},
    "groovy":       {"main": "righteous.woff",        "accent": "pacifico.woff"},
    "script_pop":   {"main": "lobster.woff",          "accent": "bebas-neue.woff"},
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
