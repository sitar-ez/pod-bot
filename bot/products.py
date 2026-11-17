"""
Which products Rory offers, and the preview-first check for new ones.

A product marked "trial" in settings.PRODUCTS (Comfort Colors tee, crewneck, tote) is held back
until Daniel approves it. Rory puts the approved Small Batch jam jar on the new product at its
real print size, gets a real Printful mockup, and sends it to Telegram with buttons:
  ✅ Use it     -> the product is added to new designs
  ✏️ Adjust     -> Daniel types the change ("1 inch lower, 10% smaller"); Rory redoes the preview
Live listings are never switched without asking.
"""
from PIL import Image

from . import llm, printful, render, settings, telegram
from .common import DESIGNS_DIR, ROOT, http, log, now_iso, public_url

SAMPLE = "d261116-05"   # the Small Batch jam jar, Daniel's approved design
WHITE_SURFACE = {"mug", "sticker", "tote"}


def checks(state):
    return state.setdefault("product_checks", {})


def is_approved(key, state):
    cfg = settings.PRODUCTS[key]
    return not cfg.get("trial") or checks(state).get(key, {}).get("status") == "approved"


def active_products(state):
    """Products new designs can use, in order."""
    out = []
    for key, cfg in settings.PRODUCTS.items():
        if cfg.get("legacy"):
            # a legacy product stands in only while its replacement isn't approved yet
            repl = next((k for k, c in settings.PRODUCTS.items() if c.get("replaces") == key), None)
            if repl and not is_approved(repl, state):
                out.append(key)
            continue
        if is_approved(key, state):
            out.append(key)
    return out


def map_key(key, state):
    """Concepts say 'tee'; use the Bella+Canvas tee until Comfort Colors is approved."""
    cfg = settings.PRODUCTS.get(key, {})
    if cfg.get("replaces") and not is_approved(key, state):
        return cfg["replaces"]
    return key


def overrides(key, state):
    o = state.get("product_overrides", {}).get(key, {})
    return float(o.get("scale_factor", 1.0)), float(o.get("move_down_inches", 0.0))


def compose(key, src, v, layout, state):
    cfg = settings.PRODUCTS[key]
    sf, down = overrides(key, state)
    dpi = v.get("dpi") or 150
    return render.compose_print_file(src, v["w"], v["h"], cfg["fit"], layout, cfg.get("max_height", 0.62),
                                     cfg.get("scale", 1.0) * sf, shift=(down * dpi) / v["h"])


def group_for(key, garment):
    cfg = settings.PRODUCTS[key]
    if not cfg["colors"] or "white" in cfg["colors"]:
        return "white"
    return garment


def placement_note(img, v):
    dpi = v.get("dpi") or 150
    b = img.getchannel("A").getbbox()
    if not b:
        return ""
    w_in, h_in, top_in = (b[2] - b[0]) / dpi, (b[3] - b[1]) / dpi, b[1] / dpi
    return f"Design about {w_in:.1f} × {h_in:.1f} in, {top_in:.1f} in below the top of the print area."


# ---------------------------------------------------------------------------
def run_checks(state):
    """Called every run: move each new product one step through its preview check."""
    sample = state["designs"].get(SAMPLE)
    master_path = DESIGNS_DIR / SAMPLE / "master.png"
    if not sample or not master_path.exists():
        return
    for key, cfg in settings.PRODUCTS.items():
        if not cfg.get("trial"):
            continue
        c = checks(state).setdefault(key, {"status": "new"})
        if c["status"] == "new":
            info = printful.resolve_product(key, state)
            master = Image.open(master_path).convert("RGBA")
            layout = dict((sample.get("concept") or {}).get("layout") or {})
            layout["top"] = None
            group = group_for(key, "light")
            picks = {}
            for vid, v in info["variants"].items():
                if v["group"] == group and v["color"] not in picks:
                    picks[v["color"]] = vid
            folder = DESIGNS_DIR / "_product_checks" / key
            folder.mkdir(parents=True, exist_ok=True)
            files, notes = {}, {}
            for color, vid in list(picks.items())[:2]:
                v = info["variants"][vid]
                img = compose(key, master, v, layout, state)
                name = folder / f"print_{v['printfile_id']}_{c.get('round', 0)}.png"
                img.save(name, optimize=True)
                files[vid] = str(name.relative_to(ROOT))
                notes[vid] = placement_note(img, v)
            c.update({"status": "files_ready", "files": files, "notes": notes, "at": now_iso()})
            log(f"  product check {key}: print files ready")
        elif c["status"] == "files_ready":
            first = next(iter(c["files"].values()))
            if http("HEAD", public_url(first), retries=0).status_code != 200:
                continue
            info = printful.resolve_product(key, state)
            photos = []
            for vid, rel in c["files"].items():
                v = info["variants"][vid]
                urls = printful.mockups(info["product_id"], [int(vid)], info.get("placement", cfg["placement"]),
                                        public_url(rel), v["w"], v["h"])
                photos += urls[:1]
            for u in photos:
                telegram.send_photo_url(u)
            v = info["variants"][next(iter(c["files"]))]
            price = max(cfg["min_price"], v["cost"] * cfg["markup"])
            colors = sorted({info["variants"][x]["color"] for x in info["variants"]})
            text = (f"🧪 New product check: {cfg['label']} ({info['title']})\n"
                    f"Above: your Small Batch jam jar at real print size on a Printful mockup.\n"
                    f"{c['notes'].get(next(iter(c['files'])), '')}\n"
                    f"Colors: {', '.join(colors)}\nPrintful cost from ${v['cost']:.2f}; Rory would price it "
                    f"from ${price:.2f}.\n\nUse this product for new designs?")
            telegram.send_buttons(text, [("✅ Use it", f"product_ok:{key}"), ("✏️ Adjust", f"product_adjust:{key}")])
            c["status"] = "sent"
            log(f"  product check {key}: preview sent")


ADJUST_PROMPT = """Daniel is adjusting how designs print on a {label}. His note:
\"\"\"{text}\"\"\"
Current adjustment: scale_factor {sf} (1.0 = standard size), move_down_inches {down} (positive = lower).
Return JSON only: {{"scale_factor": number, "move_down_inches": number, "reply": "one short sentence"}}
Combine his note with the current values (e.g. "10% smaller" from 1.0 -> 0.9; "an inch lower" adds 1)."""


def handle_callback(action, key, state):
    c = checks(state).get(key)
    cfg = settings.PRODUCTS.get(key)
    if not c or not cfg:
        return None
    if action == "product_ok":
        c["status"] = "approved"
        c["approved"] = now_iso()
        msg = f"✅ {cfg['label']} is in. New designs will include it."
        if cfg.get("replaces"):
            msg += (" Your live listings stay on the old shirt; tell me in Claude if you want those switched.")
        telegram.send(msg)
        return "✅ Added"
    state["editing_product"] = {"key": key, "at": now_iso()}
    telegram.send(f"What should change on the {cfg['label']}? For example: \"1 inch lower\", "
                  "\"10% smaller\", \"bigger and higher\".")
    return "✏️ Tell me what to change"


def handle_adjust(key, text, state):
    cfg = settings.PRODUCTS[key]
    sf, down = overrides(key, state)
    out = llm.ask_json("You turn short placement notes into numbers.",
                       ADJUST_PROMPT.format(label=cfg["label"], text=text, sf=sf, down=down))
    state.setdefault("product_overrides", {})[key] = {
        "scale_factor": max(0.5, min(1.6, float(out.get("scale_factor", sf)))),
        "move_down_inches": max(-4.0, min(8.0, float(out.get("move_down_inches", down))))}
    c = checks(state)[key]
    c["status"] = "new"
    c["round"] = c.get("round", 0) + 1
    telegram.send(f"✏️ {out.get('reply', 'Adjusted.')} A new preview is coming on the next run.")
