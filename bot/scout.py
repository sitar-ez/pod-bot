"""
Trend Scout + Compliance Checker.
Reads news and trend feeds, asks Claude for product concepts, then has a
second, stricter Claude pass throw out anything risky.
"""
import re
from datetime import date

import feedparser

from . import brief, llm, settings, skills
from .common import log

SCOUT_SYSTEM = """You are the creative director of a small Etsy print-on-demand shop.
You turn cultural signals into designs people buy as gifts or for themselves.

Hard rules (a design that breaks any of these gets the shop suspended):
- No trademarks, brand names, product names, company names, logos, team names, leagues.
- No real people's names, likenesses, nicknames or catchphrases (celebrities, politicians, athletes, influencers).
- No song lyrics, movie/TV/book/game quotes, character names, or references only a fan would recognize as owned IP.
- No politics, elections, parties, candidates, culture-war slogans.
- No tragedies, disasters, crimes, deaths, illness, war.
- No sexual content, slurs, insults about groups, drugs, or anything a buyer might find hurtful.
- Nothing that copies a phrase already famous as someone else's slogan.

What sells:
- Feelings, identities, hobbies, pets, jobs, life stages, inside jokes of a large community,
  seasonal moments, wholesome humor, gentle sarcasm, self-care, nature.
- Use the news as a SIGNAL of what people care about right now, then make something that
  will still feel right in 6 months. Never make a design that only works this week.
- Text must be short and instantly readable on a shirt across a room."""

SCOUT_PROMPT = """Today is {today}.

Here are today's headlines and trending searches:
{headlines}

Designs we already made (do not repeat these ideas or wording):
{recent}

{brief}

Create exactly {n_text} TEXT designs and {n_ill} ILLUSTRATION designs.

Return JSON only, in this shape:
{{"concepts": [
  {{
    "kind": "text" or "illustration",
    "trend_signal": "which headline/trend inspired it, in a few words",
    "why_it_sells": "one sentence: who buys it and why",
    "lines": ["LINE ONE", "line two"],
    "accent_line": 0,
    "style": a style name from the menu below,
    "ink_dark": "#hex color that reads well on white/light fabric",
    "ink_light": "#hex color that reads well on black/navy fabric",
    "garment": "light" or "dark",
    "layout": {{"width": 0.78, "top": 0.07, "line_gap": 1.0, "align": "center"}},
    "illustration_prompt": "for illustrations only: describe the image",
    "titles": {{"tee": "...", "hoodie": "...", "mug": "...", "sticker": "..."}},
    "tags": ["13 tags", "each under 20 characters", "buyer search phrases"],
    "description": "2 to 3 warm, plain sentences for the listing. No hype words.",
    "products": ["tee", "hoodie", "mug", "sticker"]
  }}
]}}

Font style menu (grouped by category):
{styles}

Notes:
- TEXT designs: 1 to 4 lines, each line at most 22 characters. "accent_line" is the index of
  the one line to render in a script/accent font, or null for none. Pick a style that suits
  the mood. lines can include simple punctuation but no emoji.
- layout: width is the share of the 12 inch print width the design uses. 0.78 is a standard
  chest print; use 0.55 to 0.65 for short phrases or small, tasteful prints; up to 0.9 only for
  bold statement pieces. top 0.07 is standard (about 1 inch below the top of the print area).
- ILLUSTRATION designs: "garment" must be "light". The prompt should describe a single
  centered subject in a bold, clean, screen-print style with a limited color palette.
  Do not ask for a background. You may include up to 4 words of text in the image only if
  it really helps; otherwise none. "lines" should be [].
- Titles: up to 140 characters, front-load what a buyer would type into Etsy search,
  e.g. "Funny Gardening Shirt, Plant Lover Gift, ...". Each title must fit its product.
- products: drop any product the design would not suit (e.g. long text on a sticker is fine,
  a very tall design on a mug is not).
"""

CHECK_SYSTEM = """You are a cautious trademark and marketplace-policy reviewer for an Etsy shop.
You reject anything with meaningful risk. When unsure, reject."""

CHECK_PROMPT = """Review each design concept below. Reject it if ANY of these apply:
- contains or closely imitates a trademark, brand, product, company, team, or registered slogan
- names or clearly refers to a real person
- quotes or references a song, film, show, book, game, meme owned by someone, or a character
- political, tragic, sexual, hateful, medical claims, or likely to offend
- the exact phrase is famous as someone else's slogan or is a known best-selling Etsy design
- the text is confusing, misspelled or unlikely to make sense to a buyer

Concepts:
{concepts}

Return JSON only: {{"verdicts": [{{"index": 0, "ok": true or false, "reason": "short"}}]}}"""

# Belt and braces: words that should never reach a listing
BLOCKLIST = re.compile(
    r"\b(disney|marvel|nike|adidas|nfl|nba|mlb|nhl|fifa|pixar|pokemon|barbie|taylor swift|swiftie|"
    r"trump|biden|maga|starbucks|stanley cup|lego|star wars|harry potter|olympic|"
    r"coca[- ]cola|pepsi|iphone|tesla|minecraft|fortnite|hello kitty|sanrio|labubu)\b",
    re.I,
)


def fetch_headlines(limit_per_feed=25):
    seen, out = set(), []
    for url in settings.FEEDS:
        try:
            feed = feedparser.parse(url, agent="Mozilla/5.0 (pod-bot)")
            for e in feed.entries[:limit_per_feed]:
                title = re.sub(r"\s+-\s+[^-]+$", "", e.get("title", "")).strip()  # drop " - Source"
                if title and title.lower() not in seen:
                    seen.add(title.lower())
                    out.append(title)
        except Exception as ex:  # one bad feed shouldn't stop the run
            log("  feed failed:", url, ex)
    log(f"  read {len(out)} headlines/trends")
    return out


def style_menu(state):
    """Styles grouped by category, plus what was used lately, so Rory keeps a varied mix."""
    groups = {}
    for k, v in settings.TEXT_STYLES.items():
        groups.setdefault(v.get("category", "other"), []).append(f"    {k}: {v['mood']}")
    order = ["sans", "serif", "geometric", "script", "other"]
    menu = "\n".join(f"  {c.upper()}\n" + "\n".join(groups[c]) for c in order if c in groups)
    recent = [((d.get("concept") or {}).get("style")) for d in list(state["designs"].values())[-12:]
              if d.get("kind") == "text"]
    recent = [r for r in recent if r]
    cats = [settings.TEXT_STYLES.get(r, {}).get("category", "?") for r in recent]
    counts = {c: cats.count(c) for c in order}
    menu += ("\n\nKeep the look varied, like a real shop with range:\n"
             "- Choose the style that best fits each message's mood first.\n"
             f"- Don't reuse these recently used styles: {', '.join(recent[-6:]) or 'none yet'}.\n"
             f"- Recent category counts: {counts}. Favor the categories used least, so over a day the shop "
             "shows a real mix of sans, serif, geometric, script/handwriting and other.\n"
             "- Within one batch, give each text design a different category.")
    return menu


def plan_mix(state, n):
    """Keep the running mix close to 70% text / 30% illustration."""
    c = state["counts"]
    total = c["text"] + c["illustration"] + n
    target_ill = round(total * settings.ILLUSTRATION_SHARE)
    n_ill = max(0, min(n, target_ill - c["illustration"]))
    return n - n_ill, n_ill


def scout(state):
    headlines = fetch_headlines()
    if not headlines:
        raise RuntimeError("No headlines could be read from any feed.")
    recent = [
        " / ".join(d.get("lines") or [d.get("illustration_prompt", "")[:60]])
        for d in list(state["designs"].values())[-80:]
    ]
    n_text, n_ill = plan_mix(state, settings.DESIGNS_PER_BATCH)
    log(f"  asking for {n_text} text + {n_ill} illustration concepts")
    data = llm.ask_json(
        SCOUT_SYSTEM,
        SCOUT_PROMPT.format(
            today=date.today().strftime("%A, %B %d, %Y"),
            headlines="\n".join(f"- {h}" for h in headlines[:150]),
            recent="\n".join(f"- {r}" for r in recent) or "- (none yet)",
            n_text=n_text,
            n_ill=n_ill,
            styles=style_menu(state),
            brief=brief.prompt_block(state) + "\n\n" + skills.prompt_block(),
        ),
    )
    brief.used_topics(state)
    concepts = data.get("concepts", [])
    return compliance(concepts)


def compliance(concepts):
    if not concepts:
        return []
    import json

    slim = [
        {"index": i, "kind": c.get("kind"), "lines": c.get("lines"),
         "illustration_prompt": c.get("illustration_prompt"), "titles": c.get("titles"),
         "tags": c.get("tags")}
        for i, c in enumerate(concepts)
    ]
    verdicts = llm.ask_json(CHECK_SYSTEM, CHECK_PROMPT.format(concepts=json.dumps(slim, indent=1)))
    ok_idx = {v["index"] for v in verdicts.get("verdicts", []) if v.get("ok")}
    passed = []
    for i, c in enumerate(concepts):
        blob = " ".join([*(c.get("lines") or []), c.get("illustration_prompt") or "",
                         *(c.get("titles") or {}).values(), *(c.get("tags") or [])])
        if i not in ok_idx:
            reason = next((v.get("reason") for v in verdicts.get("verdicts", []) if v.get("index") == i), "")
            log(f"  rejected by checker: {c.get('lines') or c.get('illustration_prompt', '')[:50]} ({reason})")
        elif BLOCKLIST.search(blob):
            log(f"  rejected by blocklist: {c.get('lines')}")
        else:
            passed.append(c)
    log(f"  {len(passed)}/{len(concepts)} concepts passed the checks")
    return passed
