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
    "What homestead, canning, baking and backyard-chicken shirts and mugs are selling on Etsy right now",
    "Vintage seed packet, recipe card and canning label design: layout, type and color",
    "Gifts for grandma and mom on Etsy: what buyers search for and what gets them to buy",
    "Cottagecore and farmhouse color palettes that print well on apparel and mugs",
    "Writing warm, funny homestead slogans: what the community jokes about (chickens, zucchini, sourdough)",
    "Typography for t-shirt slogans: serif and script pairings that read from across a room",
    "Screen-print style food and garden illustration: limited palettes, line weight, simple bold shapes",
    "Etsy SEO for gift listings: titles, tags and first photos that win gift searches",
    "Comfort Colors and garment-dyed tees: which ink colors look best on muted fabrics",
    "Upcoming gifting moments in the next 6 to 8 weeks for moms, grandmas and homesteaders",
    "Tote bag and mug design that sells: farmers market and kitchen gifts",
    "Common print-on-demand design mistakes: resolution, thin lines, transparency, colors that print badly",
    "How top Etsy homestead and kitchen-gift shops build a cohesive brand look",
    "Backyard chicken, garden and sourdough community trends and in-jokes this season",
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


def search_text(prompt, max_searches=5, max_tokens=4000):
    """Ask Claude with web search on, following pause_turn continuations. Returns all the text."""
    client = llm.client()
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}]
    messages = [{"role": "user", "content": prompt}]
    texts = []
    for _ in range(4):
        msg = client.messages.create(model=settings.CLAUDE_MODEL, max_tokens=max_tokens,
                                     system=brief.SYSTEM, messages=messages, tools=tools)
        from . import costs
        costs.claude(msg)
        texts.append("".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text"))
        if msg.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": msg.content}]
    if msg.stop_reason == "max_tokens":
        log("  research answer was cut off at the length limit; using what came back")
    return "".join(texts)


def search_json(prompt, max_searches=5, max_tokens=4000):
    return llm.parse_json(search_text(prompt, max_searches, max_tokens))


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
