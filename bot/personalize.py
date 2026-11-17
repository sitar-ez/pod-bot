"""
Personalized name designs (text designs only, no extra charge, Daniel approves every proof).

How it works
- When Rory makes a text design with a family name (like "NANA'S / small batch"), that name
  becomes a slot. The listing shows "Nana" and gets a name box: buyers type the name their
  family uses (up to 10 letters).
- When an order comes in, Rory typesets the design with the buyer's name and sends Daniel a
  proof on Telegram with ✅ Print it / ✋ Hold buttons. Nothing goes to Printful until he taps
  Print it; the next run then sends the order.
"""
import io
import re

from PIL import Image

from . import direction, printful, products, render, settings, telegram
from .common import DESIGNS_DIR, ROOT, log, now_iso

MAX_CHARS = 10
QUESTION = {
    "question_text": "Name to print",
    "instructions": "What does your family call her? Up to 10 letters, like Nana, Mimi or Mom-Mom. "
                    "We'll print it exactly as you type it.",
    "question_type": "text_input",
    "required": True,
    "max_allowed_characters": MAX_CHARS,
}
DESCRIPTION = ("\n\nPersonalize it\nType the name your family uses in the personalization box "
               "(up to 10 letters). Keep it as shown if that's her name. We check every name by hand "
               "before printing.")
OK_CHARS = re.compile(r"[^A-Za-zÀ-ſ' .\-]")
BAD = re.compile(r"\b(fuck|shit|bitch|ass|damn|hell|sex|nazi|kill|dick|cunt|whore|slut)\w*", re.I)


def make_slot(concept):
    """If a text design carries a family name, return the slot (sample name + template lines)."""
    if concept.get("kind") != "text":
        return None
    lines = concept.get("lines") or []
    for i, line in enumerate(lines):
        m = direction.NAME_RE.search(line)
        if m:
            sample = m.group(0)
            tmpl = list(lines)
            tmpl[i] = line[:m.start()] + "{NAME}" + line[m.end():]
            return {"sample": sample.title() if sample.isupper() else sample, "template": tmpl,
                    "line": i, "upper": line.isupper()}
    return None


def clean(name):
    """Tidy what the buyer typed. Returns (clean_name, warnings)."""
    warn = []
    raw = (name or "").strip()
    n = OK_CHARS.sub("", raw).strip()
    if n != raw:
        warn.append(f"removed unusual characters from \"{raw}\"")
    if len(n) > MAX_CHARS:
        warn.append("longer than 10 letters")
    if not n:
        warn.append("no usable name; using the sample")
    if BAD.search(n):
        warn.append("might be inappropriate")
    if n and n == n.lower():
        n = n.title()
    return n, warn


def lines_for(slot, name):
    out = []
    for i, t in enumerate(slot["template"]):
        nm = name.upper() if (i == slot["line"] and slot["upper"]) else name
        out.append(t.replace("{NAME}", nm))
    return out


def render_print(design, key, vid, name, state, tag):
    """Typeset the design with the buyer's name and place it on this product. Returns (img, path)."""
    c = design["concept"]
    slot = design["personalize"]
    lines = lines_for(slot, name)
    garment = design["garment"]
    white_surface = key in products.WHITE_SURFACE
    ink = c.get("ink_dark", "#1d1d1f") if (white_surface or garment == "light") else c.get("ink_light", "#f5f1e8")
    layout = dict(c.get("layout") or {})
    master = render.render_text(lines, c.get("style"), ink, c.get("accent_line"), layout)
    v = printful.resolve_product(key, state)["variants"][vid]
    img = products.compose(key, master, v, layout, state)
    folder = DESIGNS_DIR / design["id"] / "orders"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{tag}_{key}_{v['printfile_id']}.png"
    img.save(path, optimize=True)
    return img, str(path.relative_to(ROOT)), v


def proof_jpg(img, v, key):
    if key in ("tee", "tee_bc", "hoodie", "crewneck"):
        full = Image.open(io.BytesIO(render.preview(img, None, v.get("color") or "White", [key])))
        out = io.BytesIO()
        full.crop((0, 0, 1020, 1000)).save(out, "JPEG", quality=90)
        return out.getvalue()
    bg = Image.new("RGB", (img.width, img.height), (250, 250, 250))
    bg.paste(img, (0, 0), img)
    bg.thumbnail((1600, 1600))
    out = io.BytesIO()
    bg.save(out, "JPEG", quality=88)
    return out.getvalue()


def buyer_name(transaction):
    """Read the personalization the buyer typed from an Etsy transaction."""
    for v in transaction.get("variations") or []:
        label = f"{v.get('formatted_name', '')} {v.get('property_id', '')}".lower()
        if "personaliz" in label or "name to print" in label:
            return v.get("formatted_value") or v.get("value") or ""
    p = transaction.get("personalization")
    if isinstance(p, str):
        return p
    if isinstance(p, list) and p:
        return p[0].get("answer") or p[0].get("value") or ""
    return ""


def request_ok(rid, personal, state):
    """Send Daniel the proofs for one order, with Print it / Hold buttons."""
    for p in personal:
        telegram.send_photo_bytes(p["proof"], f"Proof for Etsy order #{rid}: {p['product']} with \"{p['name']}\""
                                  + (f"\n⚠️ {', '.join(p['warnings'])}" if p["warnings"] else ""))
    telegram.send_buttons(
        f"✍️ Personalized order #{rid}: {len(personal)} item(s). Check the proof(s) above. "
        "Nothing prints until you tap Print it. If you tap Hold, message the buyer on Etsy and tell "
        "me in Claude what to change.",
        [("✅ Print it", f"order_ok:{rid}"), ("✋ Hold", f"order_hold:{rid}")])


def handle_callback(action, rid, state):
    o = state["orders"].get(rid)
    if not o or o.get("status") != "awaiting_ok":
        return "Already handled"
    if action == "order_ok":
        o["status"] = "approved"
        o["approved"] = now_iso()
        telegram.send(f"✅ Order #{rid} approved. It goes to Printful on the next run.")
        return "✅ Approved"
    o["status"] = "held"
    telegram.send(f"✋ Order #{rid} is on hold. Nothing was sent to Printful.")
    return "✋ Held"
