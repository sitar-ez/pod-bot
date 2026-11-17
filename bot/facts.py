"""Insider facts bank: researched once a week, used by every batch.

Daniel's rule (Nov 17): never generic. Every design is built on a specific, true detail the
homestead buyer would love. Researching that on every run was too costly, so Rory now does
one research session a week (Monday's first run) and saves about 40 facts. Each batch picks
from the unused ones. /facts on Telegram lists them; /facts new rebuilds the bank on the next run.
"""
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from . import direction, settings
from .common import log, now_iso

PROMPT = """Research a bank of insider details for an Etsy print-on-demand shop whose buyers are
homesteaders, gardeners, canners, bakers and backyard-chicken keepers (mostly women 30 to 65,
practical, warm, a little wry), and the daughters who buy them gifts.

The shop's themes:
{themes}

Find {n} specific, TRUE, delightful details that insiders know and would smile at on a shirt or mug:
named heirloom varieties and how they got their names, seed-saving lore, old almanac or farm sayings,
the chores and small rituals of canning, baking and keeping hens, shared mishaps (zucchini overload,
hornworms, the jar that didn't seal), surprising history or science. Spread them across all the themes,
and favor the season ahead ({season}).

Rules:
- Every fact must be confirmed by a reliable source you found (extension services, seed savers,
  museums, reputable publications). Give the URL.
- No real people's names (no breeders, authors, celebrities). Common variety names sold by many seed
  companies are fine. No brand names or trademarks. No religion or politics.
- Skip anything already in this list: {used}

Return JSON only:
{{"facts": [{{"theme": "short theme name", "fact": "one plain sentence",
             "angle": "a short idea for how it could become a design (a phrase or picture)",
             "source": "URL"}}]}}"""


def due(state):
    f = state.get("facts") or {}
    if f.get("rebuild") or not f.get("items"):
        return True
    local = datetime.now(ZoneInfo(settings.WORK_TIMEZONE))
    built = f.get("built", "")[:10]
    fresh = [x for x in f["items"] if not x.get("used")]
    return (local.weekday() == 0 and built != local.strftime("%Y-%m-%d")) or len(fresh) < 6


def build(state):
    from .study import search_json
    f = state.setdefault("facts", {})
    used = [x["fact"][:80] for x in f.get("items", []) if x.get("used")][-60:]
    month = datetime.now(ZoneInfo(settings.WORK_TIMEZONE)).strftime("%B")
    out = search_json(PROMPT.format(themes="\n".join(f"- {t}" for t in direction.THEMES), n=40,
                                    season=f"it's {month} now", used="; ".join(used) or "none"),
                      max_searches=8, max_tokens=10000)
    items = [x for x in out.get("facts", []) if x.get("fact") and x.get("source")]
    if not items:
        raise RuntimeError("the research came back empty; keeping the old bank")
    start = max([x.get("id", 0) for x in f.get("items", [])] + [0]) + 1
    for i, x in enumerate(items):
        x["id"] = start + i
    keep_used = [x for x in f.get("items", []) if x.get("used")][-60:]
    f.update(items=keep_used + items, built=now_iso(), rebuild=False)
    log(f"  fact bank: {len(items)} new insider details")


def prompt_block(state, k=10):
    items = [x for x in (state.get("facts") or {}).get("items", []) if not x.get("used")]
    if not items:
        return ""
    pick = random.sample(items, min(k, len(items)))
    rows = "\n".join(f"- [{x['id']}] ({x.get('theme', '')}) {x['fact']} Idea: {x.get('angle', '')}" for x in pick)
    return ("INSIDER DETAILS (researched and verified; build each design on one of these, or on another "
            "detail you're certain is true and just as specific. Never make a design that only names its "
            "subject. Put the id in \"fact_id\"):\n" + rows)


def mark_used(state, concepts):
    items = {x["id"]: x for x in (state.get("facts") or {}).get("items", [])}
    for c in concepts:
        try:
            x = items.get(int(c.get("fact_id")))
        except (TypeError, ValueError):
            x = None
        if x:
            x["used"] = now_iso()
            c.setdefault("insider_fact", x["fact"])
            c["fact_source"] = x.get("source")


def listing(state):
    items = (state.get("facts") or {}).get("items", [])
    fresh = [x for x in items if not x.get("used")]
    if not fresh:
        return "The insider facts bank is empty. It fills up on the next run."
    lines = [f"🔎 Insider facts bank: {len(fresh)} unused (built {(state['facts'].get('built') or '')[:10]})"]
    lines += [f"{x['id']}. {x['fact']}" for x in fresh[:25]]
    lines.append("\n/facts new  research a fresh bank on the next run")
    return "\n".join(lines)
