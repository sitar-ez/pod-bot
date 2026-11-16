"""
Daily study. On the first run of each workday Rory researches one design skill on
the web (Claude's built-in web search), keeps 3 to 5 practical lessons, and tells
you on Telegram what it learned. Topics rotate through the curriculum below.

Lessons Rory teaches itself start with 📖. Your own lessons always win if they
disagree. Use /lessons to see them and /forget N to drop one.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from . import brief, llm, settings, telegram
from .common import log, now_iso

CURRICULUM = [
    "Typography for t-shirt slogans: font pairing, hierarchy, readability from across a room",
    "Choosing ink colors for apparel: light vs dark garments, heather fabrics, contrast",
    "What t-shirt and hoodie niches are selling well on Etsy right now",
    "Writing funny or heartfelt shirt slogans that sell: wordplay, specificity, identity",
    "Screen-print style illustration: limited palettes, line weight, simple bold shapes",
    "Composition and placement for chest prints and full-front prints",
    "Etsy SEO for print-on-demand: titles, tags and first photos that get clicks",
    "Mug design that sells: wrap vs both sides, sizing, gift angles",
    "Sticker design that sells: shapes, borders, small-size readability",
    "Upcoming seasonal and holiday gifting moments in the next 6 to 8 weeks and how designers approach them",
    "Retro and vintage design trends on apparel: badges, distressed type, 70s palettes",
    "Minimalist line art and small tasteful prints that sell",
    "Common print-on-demand design mistakes: resolution, thin lines, transparency, colors that print badly",
    "How top Etsy apparel shops build a cohesive brand look across many designs",
]

STUDY_PROMPT = """Today's study topic for our Etsy print-on-demand shop:
"{topic}"

Use web search to find 3 to 5 good, recent sources (design blogs, print shops, Etsy seller
resources, typographers). Skip thin SEO filler. Then return JSON only:
{{"lessons": ["3 to 5 short, specific, practical rules you'll follow when making designs"],
  "topics": ["0 to 2 niches or themes worth designing for, if the research suggests any"],
  "summary": "2 to 3 plain, warm sentences to Daniel about what you learned",
  "sources": ["the 2 to 4 most useful URLs"]}}

Rules: never suggest trademarks, brands, real people or politics. Lessons must be things you
can actually apply to text layouts, fonts, colors, illustration prompts, titles or tags."""


def search_json(prompt, max_searches=5):
    """Ask Claude with web search on, following pause_turn continuations."""
    client = llm.client()
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}]
    messages = [{"role": "user", "content": prompt}]
    for _ in range(4):
        msg = client.messages.create(model=settings.CLAUDE_MODEL, max_tokens=4000,
                                     system=brief.SYSTEM, messages=messages, tools=tools)
        if msg.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": msg.content}]
    text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
    return llm.parse_json(text)


def due(state):
    today = datetime.now(ZoneInfo(settings.WORK_TIMEZONE)).strftime("%Y-%m-%d")
    return state.get("study_force") or state.get("last_study") != today


def study(state):
    custom = state.pop("study_force", None)
    if isinstance(custom, str) and custom.strip():
        topic = custom.strip()
    else:
        i = state.get("study_index", 0)
        topic = CURRICULUM[i % len(CURRICULUM)]
        state["study_index"] = i + 1
    log(f"  studying: {topic}")
    out = search_json(STUDY_PROMPT.format(topic=topic))
    lessons = ["📖 " + x.strip() for x in out.get("lessons", []) if x.strip()]
    b = brief._brief(state)
    brief._add(b, out.get("topics", []), lessons)
    state["last_study"] = datetime.now(ZoneInfo(settings.WORK_TIMEZONE)).strftime("%Y-%m-%d")
    state.setdefault("study_log", []).append({"date": now_iso(), "topic": topic, "lessons": lessons,
                                              "sources": out.get("sources", [])})
    state["study_log"] = state["study_log"][-60:]
    msg = (f"📖 Today I studied: {topic}\n\n{out.get('summary', '')}\n\nNew lessons:\n" +
           "\n".join(f"• {x[2:]}" for x in lessons))
    if out.get("topics"):
        msg += "\n\nIdeas to explore: " + ", ".join(out["topics"])
    if out.get("sources"):
        msg += "\n\nSources:\n" + "\n".join(out["sources"][:4])
    msg += "\n\nDisagree with any of these? Send /lessons and /forget the number."
    telegram.send(msg)
