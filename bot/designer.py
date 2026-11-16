"""Designer: turns approved-by-checker concepts into files and sends them to Telegram."""
from datetime import datetime

from . import printful, render, settings, telegram
from .common import DESIGNS_DIR, ROOT, log, now_iso

WHITE_SURFACE = {"mug", "sticker"}   # products that are always white


def new_id(state):
    stamp = datetime.now().strftime("%y%m%d")
    n = sum(1 for k in state["designs"] if k.startswith(f"d{stamp}")) + 1
    return f"d{stamp}-{n:02d}"


def make_design(concept, state):
    did = new_id(state)
    folder = DESIGNS_DIR / did
    folder.mkdir(parents=True, exist_ok=True)
    kind = concept.get("kind", "text")
    products = [p for p in concept.get("products", list(settings.PRODUCTS)) if p in settings.PRODUCTS]
    garment = "light" if kind == "illustration" else concept.get("garment", "light")

    if kind == "text":
        lines = concept["lines"][:4]
        style, accent = concept.get("style"), concept.get("accent_line")
        ink_dark = concept.get("ink_dark", "#1d1d1f")
        ink_light = concept.get("ink_light", "#f5f1e8")
        apparel = render.render_text(lines, style, ink_light if garment == "dark" else ink_dark, accent)
        white = apparel if garment == "light" else render.render_text(lines, style, ink_dark, accent)
    else:
        apparel = render.render_illustration(concept["illustration_prompt"])
        white = apparel

    apparel.save(folder / "master.png")
    if white is not apparel:
        white.save(folder / "master_white.png")

    # One print file per product per print-area size
    files = {}
    for key in products:
        cfg = settings.PRODUCTS[key]
        info = printful.resolve_product(key, state)
        src = white if key in WHITE_SURFACE else apparel
        group = "white" if not cfg["colors"] else garment
        done = {}
        for vid, v in info["variants"].items():
            if v["group"] != group:
                continue
            pfid = v["printfile_id"]
            if pfid not in done:
                name = f"print_{key}_{pfid}.png"
                render.compose_print_file(src, v["w"], v["h"], cfg["fit"]).save(folder / name, optimize=True)
                done[pfid] = str((folder / name).relative_to(ROOT))
            files.setdefault(key, {})[vid] = done[pfid]

    record = {
        "id": did, "kind": kind, "status": "pending", "created": now_iso(),
        "garment": garment, "products": [p for p in products if p in files], "files": files,
        "lines": concept.get("lines", []), "illustration_prompt": concept.get("illustration_prompt"),
        "titles": concept.get("titles", {}), "tags": concept.get("tags", []),
        "description": concept.get("description", ""), "trend_signal": concept.get("trend_signal", ""),
        "why_it_sells": concept.get("why_it_sells", ""), "listings": {},
    }

    first_color = (settings.PRODUCTS["tee"]["colors"] or {}).get(garment, ["White"])[0]
    jpg = render.preview(apparel, white, first_color, record["products"])
    (folder / "preview.jpg").write_bytes(jpg)
    what = " / ".join(record["lines"]) if kind == "text" else (record["illustration_prompt"] or "")[:160]
    caption = (
        f"🆕 {did} · {kind}\n\n{what}\n\n"
        f"📈 Trend: {record['trend_signal']}\n"
        f"🛍 {record['why_it_sells']}\n"
        f"Products: {', '.join(record['products'])} · {garment} garments\n\n"
        "Quick check before approving: is this phrase or image owned by anyone? "
        "Search it on Etsy and Google if unsure."
    )
    record["telegram_msg"] = telegram.send_design(jpg, caption, did)
    state["designs"][did] = record
    state["counts"][kind] = state["counts"].get(kind, 0) + 1
    log(f"  made {did}: {what[:70]}")
    return record
