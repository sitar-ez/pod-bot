"""Designer: turns checked concepts into files and sends them to Telegram."""
import json
import re
from datetime import datetime

from PIL import Image

from . import audit, llm, personalize, printful, products as prods, render, scout, settings, skills, telegram
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
    active = prods.active_products(state)
    products = []
    for p in concept.get("products") or active:
        p = prods.map_key(p, state)
        if p in active and p not in products:
            products.append(p)
    garment = "light" if (kind == "illustration" or settings.LIGHT_GARMENTS_ONLY) else concept.get("garment", "light")
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
        src = white if key in prods.WHITE_SURFACE else apparel
        group = prods.group_for(key, garment)
        done = {}
        for vid, v in info["variants"].items():
            if v["group"] != group:
                continue
            pfid = v["printfile_id"]
            if pfid not in done:
                name = f"print_{key}_{pfid}.png"
                img = prods.compose(key, src, v, layout, state)
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
        "personalize": personalize.make_slot(concept) if settings.PERSONALIZATION else None,
    }

    tee_key = next((k for k in ("tee", "tee_bc") if k in firsts), "tee_bc")
    tee_info = printful.resolve_product(tee_key, state) if tee_key in firsts else None
    first_color = next((v["color"] for v in (tee_info or {}).get("variants", {}).values() if v["group"] == garment),
                       "White")
    tee_img = firsts.get(tee_key) or firsts.get("crewneck") or firsts.get("hoodie") or render.compose_print_file(apparel, 1800, 2400, "top", layout)
    jpg = render.preview(tee_img, firsts.get("mug"), first_color, record["products"])
    (folder / "preview.jpg").write_bytes(jpg)
    what = " / ".join(record["lines"]) if kind == "text" else (record["illustration_prompt"] or "")[:160]
    head = f"✏️ {did} · revised version of {parent}" if parent else f"🆕 {did} · {kind}"
    caption = (
        f"{head}\n\n{what}\n\n"
        + (f"🔎 Insider detail: {concept['insider_fact']}\n" if concept.get("insider_fact") else "")
        + f"📈 Trend: {record['trend_signal']}\n"
        f"🛍 {record['why_it_sells']}\n"
        f"Products: {', '.join(record['products'])} · {garment} garments\n"
        + (f"✍️ Personalized: buyers can swap \"{record['personalize']['sample']}\" for their own name "
           "(you approve each proof)\n" if record["personalize"] else "") + "\n"
        "Want changes? Tap ✏️ Edit and type what to change, or just reply to this message."
    )
    record["telegram_msg"] = telegram.send_design(jpg, caption, did)
    state["designs"][did] = record
    if parent:
        audit.record(state, did, "revised", via="automatic", note=f"revision of {parent}")
    else:
        audit.record(state, did, "proposed", via="automatic", note=record["trend_signal"] or None)
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
             "top": leave it out for automatic placement (big designs about 5 in below the collar, small designs
                    about 9 in below). Only set it when he asks to move the design: 0.0-0.45 as a share of the
                    16 inch print area, which starts about 2.5 in below the collar (0.40 is about 9 in below the collar),
             "line_gap": 0.2-3.0 spacing between lines (1.0 normal),
             "line_scale": optional list, one number per line (0.25-1.0), each line's size relative to the
                           biggest; use it to fix hierarchy, e.g. [1.0, 0.8, 0.6] so a tagline isn't tiny,
             "align": "center" | "left" | "right"}}
- "illustration_prompt" for illustrations. Set "regenerate_image" true ONLY if the picture itself must change;
  for size, position or other layout changes keep it false so the same artwork is reused.
- "products", "titles", "tags", "description" if his note affects them.
Keep the same "kind". Keep everything he didn't mention.

{skills}"""


GENERIC_NOTE = re.compile(r"generic|dig deeper|go deeper|more specific|research|boring|not compelling", re.I)


def edit_design(did, instructions, state, via="Telegram"):
    from . import brief
    old = state["designs"].get(did)
    if not old:
        telegram.send(f"I can't find design {did} anymore.")
        return
    audit.record(state, did, "edit_requested", note=instructions, via=via)
    concept = old.get("concept") or {
        "kind": old["kind"], "lines": old["lines"], "illustration_prompt": old.get("illustration_prompt"),
        "garment": old["garment"], "titles": old["titles"], "tags": old["tags"],
        "description": old["description"], "products": old["products"],
        "trend_signal": old.get("trend_signal"), "why_it_sells": old.get("why_it_sells"),
    }
    if GENERIC_NOTE.search(instructions or ""):   # "too generic, dig deeper": research a better idea
        from .deepen import deepen
        new = deepen([dict(concept)], note=instructions)[0]
        if not new.get("deepened") or not scout.compliance([new]):
            telegram.send(f"I looked for a more specific angle on {did} but didn't find one that passed the "
                          "checks. Try telling me a direction, like a variety, a saying or a chore.")
            return
        new["kind"] = old["kind"]
        telegram.send(f"🔎 Dug deeper on {did}: {new.get('insider_fact', '')}\nNew version below.")
        rec = make_design(new, state, parent=did)
        old["status"] = "replaced"
        audit.record(state, did, "replaced", via="automatic", note=f"replaced by {(rec or {}).get('id', 'a revision')}")
        return
    out = llm.ask_json(scout.SCOUT_SYSTEM, EDIT_PROMPT.format(
        concept=json.dumps(concept, indent=1), instructions=instructions, styles=", ".join(f"{k} ({v['mood']})" for k, v in settings.TEXT_STYLES.items()), skills=skills.prompt_block()))
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
    rec = make_design(new, state, parent=did, reuse_master=reuse)
    old["status"] = "replaced"
    audit.record(state, did, "replaced", via="automatic", note=f"replaced by {(rec or {}).get('id', 'a revision')}")
