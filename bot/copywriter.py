"""Etsy titles, tags and descriptions, written only after Daniel approves a design.

Writing them for every idea (most get skipped) was wasted spend (Daniel, Nov 17: keep API
costs low). One small Claude call per approved design, then the same safety check as ideas.
"""
import json

from . import direction, llm, scout, settings
from .common import log

PROMPT = """Daniel approved this design for the Etsy shop. Write its listing copy.

Design:
{design}

Products to list: {products}

{avatars}

TITLE AND TAG PHRASES to draw from: {buyer_tags}

Return JSON only:
{{"titles": {{{title_keys}}},
  "tags": ["13 tags", "each under 20 characters", "buyer search phrases"],
  "description": "2 to 3 warm, plain sentences for the listing. No hype words."}}

Rules:
- Titles: up to 140 characters each. Front-load what a buyer would type into Etsy search and who it's
  a gift for, e.g. "Nana's Small Batch Jam Shirt, Canning Gift for Grandma, ...". Each title must fit
  its product (shirt, hoodie, mug, sticker, tote...).
- Tags: exactly 13, each 20 characters or fewer, no repeats.
- No trademarks, brand names, real people or religious words. Don't call it handmade.
- If the design has an insider detail, the description can explain it in one friendly sentence.{extra}"""


def write(design, state):
    """Fill design['titles'], ['tags'], ['description']. Returns True if it passed the checks."""
    keys = design["products"]
    brief = {k: design.get(k) for k in ("kind", "lines", "illustration_prompt", "trend_signal", "why_it_sells")}
    brief["insider_fact"] = (design.get("concept") or {}).get("insider_fact")
    for attempt in range(2):
        out = llm.ask_json(scout.SCOUT_SYSTEM, PROMPT.format(
            design=json.dumps(brief, indent=1),
            products=", ".join(f"{k} ({settings.PRODUCTS[k]['label']})" for k in keys),
            avatars=direction.AVATARS, buyer_tags=direction.BUYER_TAGS,
            title_keys=", ".join(f'"{k}": "..."' for k in keys),
            extra=("\n- For the tee, include \"Comfort Colors\" in its title and one tag."
                   if "tee" in keys and settings.PRODUCTS["tee"].get("comfort_colors") else "")), max_tokens=2000)
        check = {**brief, "titles": out.get("titles") or {}, "tags": out.get("tags") or []}
        if scout.compliance([check]):
            design["titles"] = out.get("titles") or {}
            design["tags"] = out.get("tags") or []
            design["description"] = out.get("description") or ""
            log(f"  wrote listing copy for {design['id']}")
            return True
        log(f"  listing copy for {design['id']} failed the check (try {attempt + 1})")
    return False
