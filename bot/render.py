"""
Turns concepts into print-ready PNGs.
- Text designs are typeset here with open-license fonts (no AI, crisp at any size).
- Illustrations come from OpenAI's image model with a transparent background.
- Each design is then fitted into the exact print area of every product.
"""
import base64
import io

from PIL import Image, ImageDraw, ImageFont

from . import settings
from .common import FONTS_DIR, env, http, log, raise_for

MASTER_W = 4500  # 15 inches at 300 dpi


def hex_rgb(h, fallback=(20, 20, 20)):
    try:
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return fallback


def _font_for_width(path, text, target_w, max_h):
    """Largest font size where the text fits target_w wide and max_h tall."""
    lo, hi, best = 20, 2400, 20
    while lo <= hi:
        mid = (lo + hi) // 2
        f = ImageFont.truetype(str(path), mid)
        l, t, r, b = f.getbbox(text)
        if (r - l) <= target_w and (b - t) <= max_h:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    return ImageFont.truetype(str(path), best)


DEFAULT_LAYOUT = {"width": 0.78, "top": None, "line_gap": 1.0, "align": "center"}
# Printful's print area starts about 2.5 in below the collar and is 16 in tall.
TOP_FULL = 0.03    # full-size designs: top edge about 3 in below the collar
TOP_SMALL = 0.40   # small designs: top edge about 9 in below the collar (Daniel's rule)
SMALL_WIDTH = 0.62 # narrower than about 7.5 in ...
SMALL_HEIGHT = 0.35 # ... and shorter than about 5.5 in counts as small


def layout_of(d):
    lay = dict(DEFAULT_LAYOUT)
    lay.update({k: v for k, v in (d or {}).items() if v is not None and k in DEFAULT_LAYOUT})
    lay["width"] = min(1.0, max(0.25, float(lay["width"])))
    if lay["top"] is not None:
        lay["top"] = min(0.45, max(0.0, float(lay["top"])))
    lay["line_gap"] = min(3.0, max(0.2, float(lay["line_gap"])))
    if lay["align"] not in ("center", "left", "right"):
        lay["align"] = "center"
    return lay


def render_text(lines, style, ink_hex, accent_line=None, layout=None):
    lay = layout_of(layout)
    st = settings.TEXT_STYLES.get(style) or settings.TEXT_STYLES["bold_stack"]
    ink = (*hex_rgb(ink_hex), 255)
    target_w = int(MASTER_W * 0.94)
    items = [(i, l.strip()) for i, l in enumerate(lines) if l.strip()]
    is_acc = lambda i: accent_line is not None and i == accent_line and len(items) > 1
    # Size the longest lead line first; every other line is capped relative to it, so a short
    # word or the accent line supports the lead instead of towering over it.
    leads = [(i, t) for i, t in items if not is_acc(i)] or items
    ref_i, ref_t = max(leads, key=lambda it: len(it[1]))
    f = _font_for_width(FONTS_DIR / st["main"], ref_t, target_w, 1300)
    l, t, r, b = f.getbbox(ref_t)
    ref_h = b - t
    rendered = []
    for i, line in items:
        accent = is_acc(i)
        font_file = FONTS_DIR / (st["accent"] if accent else st["main"])
        max_h = int(ref_h * (0.8 if accent else 1.15)) if i != ref_i else 1300
        width = target_w if accent or len(line) > 6 else int(target_w * 0.7)
        f = _font_for_width(font_file, line, width, max_h)
        l, t, r, b = f.getbbox(line)
        img = Image.new("RGBA", (r - l + 40, b - t + 40), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((20 - l, 20 - t), line, font=f, fill=ink)
        rendered.append(img)
    if not rendered:
        raise ValueError("Text design has no lines")
    gap = int(110 * lay["line_gap"])
    h = sum(im.height for im in rendered) + gap * (len(rendered) - 1)
    canvas = Image.new("RGBA", (MASTER_W, h + 80), (0, 0, 0, 0))
    y = 40
    for im in rendered:
        x = {"left": 0, "right": MASTER_W - im.width}.get(lay["align"], (MASTER_W - im.width) // 2)
        canvas.alpha_composite(im, (x, y))
        y += im.height + gap
    return trim(canvas)


def render_illustration(prompt):
    full_prompt = (
        f"{prompt}\n\nStyle: bold, clean, screen-print-ready artwork for a t-shirt. Crisp edges, "
        "limited color palette, strong silhouette, no drop shadows that fade into nothing, no "
        "photographic detail, no border or frame. Single centered subject."
    )
    sizes = [settings.IMAGE_SIZE, "2048x3072", "1536x2304", "1024x1536"]
    last = None
    for size in sizes:
        r = http(
            "POST", "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {env('OPENAI_API_KEY')}"},
            json={"model": settings.IMAGE_MODEL, "prompt": full_prompt, "size": size,
                  "background": "transparent", "output_format": "png", "quality": "high", "n": 1},
            timeout=300,
        )
        if r.status_code == 400 and size != sizes[-1]:
            log(f"  image size {size} refused ({r.text[:200]}), trying smaller")
            last = r
            continue
        raise_for(r, "Image generation")
        b64 = r.json()["data"][0]["b64_json"]
        img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")
        img = trim(clean_alpha(img))
        # Upscale toward print resolution
        if img.width < MASTER_W:
            scale = MASTER_W / img.width
            img = img.resize((MASTER_W, int(img.height * scale)), Image.LANCZOS)
        return img
    raise_for(last, "Image generation")


def clean_alpha(img, floor=24):
    """Remove near-invisible specks AI images leave in transparent areas; they'd print as haze."""
    a = img.getchannel("A").point(lambda v: 0 if v <= floor else v)
    img.putalpha(a)
    return img


def trim(img, pad=20):
    bbox = img.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    if not bbox:
        return img
    l, t, r, b = bbox
    return img.crop((max(0, l - pad), max(0, t - pad), min(img.width, r + pad), min(img.height, b + pad)))


def _fit(img, max_w, max_h):
    s = min(max_w / img.width, max_h / img.height)
    return img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)


def compose_print_file(master, w, h, fit, layout=None, max_height=0.62):
    """Place the design inside a canvas the exact size of Printful's print area.
    layout: width = share of the print width the design may use, top = gap above it."""
    lay = layout_of(layout)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if fit == "top":          # shirts: chest placement
        d = _fit(master, w * lay["width"], h * max_height)
        x = {"left": int(w * 0.05), "right": int(w * 0.95 - d.width)}.get(lay["align"], (w - d.width) // 2)
        top = lay["top"]
        if top is None:   # automatic: small designs sit mid-chest, big ones start near the collar
            small_top = TOP_SMALL if max_height > 0.55 else 0.22   # hoodies: stay above the pocket
            top = small_top if (d.width < w * SMALL_WIDTH and d.height < h * SMALL_HEIGHT) else TOP_FULL
            top = min(top, max(0.0, (h * 0.9 - d.height) / h))
        canvas.alpha_composite(d, (x, int(h * top)))
    elif fit == "mug":        # mugs: one copy on each side, as big as fits
        d = _fit(master, w * 0.44, h * 0.86)
        for cx in (w * 0.25, w * 0.75):
            canvas.alpha_composite(d, (int(cx - d.width / 2), (h - d.height) // 2))
    else:                     # stickers: centered, filling the sticker
        d = _fit(master, w * 0.92, h * 0.92)
        canvas.alpha_composite(d, ((w - d.width) // 2, (h - d.height) // 2))
    return canvas


# ---------------------------------------------------------------------------
# Preview image for Telegram: the design on a shirt and a mug
# ---------------------------------------------------------------------------
GARMENT_RGB = {"White": (245, 245, 243), "Athletic Heather": (196, 196, 198), "Sport Grey": (180, 182, 184),
               "Black": (24, 24, 26), "Navy": (30, 38, 62)}


def _shirt(color, size=900):
    s = size / 100
    pts = [(30, 8), (40, 12), (60, 12), (70, 8), (95, 22), (86, 40), (76, 34), (76, 96), (24, 96),
           (24, 34), (14, 40), (5, 22)]
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.polygon([(x * s, y * s) for x, y in pts], fill=(*color, 255))
    dr.chord([40 * s, 4 * s, 60 * s, 18 * s], 0, 180, fill=(0, 0, 0, 0))
    return img


# Where Printful's 12 x 16 inch front print area sits on a size M tee (body is ~20 in wide).
# In shirt units (0-100): body spans x 24..76 (2.6 units per inch); collar seam at y 18, print area ~2.5 in below.
PRINT_BOX = (34.4, 24.5, 65.6, 66.1)


def preview(tee_print, mug_print, garment_color_name, products):
    """True-to-scale preview: the real print file placed where Printful prints it."""
    W, H = 1800, 1000
    bg = Image.new("RGBA", (W, H), (236, 233, 226, 255))
    S = 900
    shirt = _shirt(GARMENT_RGB.get(garment_color_name, (245, 245, 243)), S)
    x0, y0, x1, y1 = [v * S / 100 for v in PRINT_BOX]
    shirt.alpha_composite(tee_print.resize((int(x1 - x0), int(y1 - y0)), Image.LANCZOS), (int(x0), int(y0)))
    bg.alpha_composite(shirt, (60, 60))
    if mug_print is not None and ("mug" in products or "sticker" in products):
        mug = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
        dr = ImageDraw.Draw(mug)
        dr.rounded_rectangle([60, 80, 460, 560], 30, fill=(250, 250, 250, 255), outline=(200, 200, 200, 255), width=6)
        dr.ellipse([420, 200, 580, 420], outline=(250, 250, 250, 255), width=40)
        half = mug_print.crop((0, 0, mug_print.width // 2, mug_print.height))   # one side of the mug
        face = half.resize((400, int(400 * half.height / half.width)), Image.LANCZOS)
        mug.alpha_composite(face, (60, 320 - face.height // 2))
        bg.alpha_composite(mug, (1100, 220))
    out = io.BytesIO()
    bg.convert("RGB").save(out, "JPEG", quality=88)
    return out.getvalue()
