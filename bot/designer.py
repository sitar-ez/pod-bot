"""Designer: turns checked concepts into files and sends them to Telegram."""
import json
from datetime import datetime

from PIL import Image

from . import llm, printful, render, scout, settings, telegram
from .common import DESIGNS_DIR, ROOT, log, now_iso

WHITE_SURFACE = {"mug", "sticker"}   # products that are always white


def new_id(state):
    stamp = datetime.now().strftime("%y%m%d")
    n = sum(1 for k in state["designs"] if k.startswith(f"d{stamp}")) + 1
    return f"d{stamp}-{n:02d}"


def make_design(concept, state, parent=None, reuse_master=None):
    did = new_id(state)
    folder = DESIGNS_DIR / did
    folder.mkdir(parents=True, exist_ok=True)
    kind = concept.get("kind", "text")
    products = [p for p in concept.get("products", list(settings.PRODUCTS)) if p in settings.PRODUCTS]
    garment = "light" if kind == "illustration" else concept.get("garment", "light")
    concept["garment"] = garment
    layout = render.layout_of(concept.get("layout"))
    concept["layout"] = layout

    if kind == "text":
        lines = concept["lines"][:4]
        style, accent = concept.get("style"), concept.get("accent_line")
        ink_dark = concept.get("ink_dark", "#1d1d1f")
        ink_light = concept.get("ink_light", "#f5f1e8")
        apparel = render.render_text(lines, style, ink_light if garment == "dark" else ink_dark, accent, layout)
        white = apparel if garment == "light" else render.render_text(lines, style, ink_dark, accent, layout)
    else:
        apparel = Image.open(reuse_master).convert("RGBA") if reuse_master else \
            render.render_illustration(concept["illustration_prompt"])
        white = apparel

    apparel.save(folder / "master.png")
    if white is not apparel:
        white.save(folder / "master_white.png")

    # One print file per product per print-area size
    files, firsts = {}, {}
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
                img = render.compose_print_file(src, v["w"], v["h"], cfg["fit"], layout)
                img.save(folder / name, optimize=True)
                firsts.setdefault(key, img)
                done[pfid] = str((folder / name).relative_to(ROOT))
            files.setdefault(key, {})[vid] = done[pfid]

    record = {
        "id": did, "kind": kind, "status": "pending", "created": now_iso(), "parent": parent,
        "garment": garment, "products": [p for p in products if p in files], "files": files,
        "lines": concept.get("lines", []), "illustration_prompt": concept.get("illustration_prompt"),
        "titles": concept.get("titles", {}), "tags": concept.get("tags", []),
        "description": concept.get("description", ""), "trend_signal": concept.get("trend_signal", ""),
        "why_it_sells": concept.get("why_it_sells", ""), "listings": {}, "concept": concept,
    }

    first_color = (settings.PRODUCTS["tee"]["colors"] or {}).get(garment, ["White"])[0]
    tee_img = firsts.get("tee") or firsts.get("hoodie") or render.compose_print_file(apparel, 1800, 2400, "top", layout)
    jpg = render.preview(tee_img, firsts.get("mug"), first_color, record["products"])
    (folder / "preview.jpg").write_bytes(jpg)
    what = " / ".join(record["lines"]) if kind == "text" else (record["illustration_prompt"] or "")[:160]
    head = f"✏️ {did} · revised version of {parent}" if parent else f"🆕 {did} · {kind}"
    caption = (
        f"{head}\n\n{what}\n\n"
        f"📈 Trend: {record['trend_signal']}\n"
        f"🛍 {record['why_it_sells']}\n"
        f"Products: {', '.join(record['products'])} · {garment} garments\n\n"
        "Want changes? Tap ✏️ Edit and type what to change, or just reply to this message."
    )
    record["telegram_msg"] = telegram.send_design(jpg, caption, did)
    state["designs"][did] = record
    if not parent:
        state["counts"][kind] = state["counts"].get(kind, 0) + 1
    log(f"  made {did}: {what[:70]}")
    return record


# ---------------------------------------------------------------------------
# Editing
# ---------------------------------------------------------------------------
EDIT_PROMPT = """Daniel wants changes to this design before he approves it.

Current design (JSON):
{concept}

His instructions:
\"\"\"{instructions}\"\"\"

Return the revised design as JSON only:
{{"concept": {{ ...same fields as above, changed as he asked... }},
  "regenerate_image": true or false,
  "lesson": "a standing rule for ALL future designs, only if his note clearly applies beyond this one design, else empty",
  "reply": "one short sentence telling him what you changed"}}

What you can change:
- "lines" (text designs: 1 to 4 lines, max 22 characters each), "accent_line" (index of the script-font line, or null)
- "style": one of {styles}
- "ink_dark" / "ink_light": hex colors for light / dark fabric; "garment": "light" or "dark"
- "layout": {{"width": 0.25-1.0 share of the 12 inch print width (0.78 is standard, 0.5 is a small chest print),
             "top": 0.0-0.45 gap above the design as a share of the 16 inch print height (0.07 is standard; higher moves it down),
             "line_gap": 0.2-3.0 spacing between lines (1.0 normal),
             "align": "center" | "left" | "right"}}
- "illustration_prompt" for illustrations. Set "regenerate_image" true ONLY if the picture itself must change;
  for size, position or other layout changes keep it false so the same artwork is reused.
- "products", "titles", "tags", "description" if his note affects them.
Keep the same "kind". Keep everything he didn't mention."""


def edit_design(did, instructions, state):
    from . import brief
    old = state["designs"].get(did)
    if not old:
        telegram.send(f"I can't find design {did} anymore.")
        return
    concept = old.get("concept") or {
        "kind": old["kind"], "lines": old["lines"], "illustration_prompt": old.get("illustration_prompt"),
        "garment": old["garment"], "titles": old["titles"], "tags": old["tags"],
        "description": old["description"], "products": old["products"],
        "trend_signal": old.get("trend_signal"), "why_it_sells": old.get("why_it_sells"),
    }
    out = llm.ask_json(scout.SCOUT_SYSTEM, EDIT_PROMPT.format(
        concept=json.dumps(concept, indent=1), instructions=instructions, styles=list(settings.TEXT_STYLES)))
    new = out.get("concept") or concept
    new["kind"] = old["kind"]
    if new.get("lines") != concept.get("lines") or out.get("regenerate_image"):
        if not scout.compliance([new]):
            telegram.send(f"I didn't make that change to {did}: the safety check flagged the new wording or "
                          "image as possibly owned by someone. Try a different direction.")
            return
    reuse = None
    if old["kind"] == "illustration" and not out.get("regenerate_image"):
        reuse = str(DESIGNS_DIR / did / "master.png")
    if out.get("lesson"):
        brief._add(brief._brief(state), lessons=[out["lesson"]])
    telegram.send(f"✏️ {out.get('reply', 'Revised.')} New version below.")
    make_design(new, state, parent=did, reuse_master=reuse)
    old["status"] = "replaced"
