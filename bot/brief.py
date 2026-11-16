"""
Your conversation with the bot. Anything you send on Telegram that isn't a
command lands here:
- a trend or topic ("look into cold plunge culture")  -> explored in upcoming batches
- a link to an article                                 -> read, and the design lessons kept
- feedback or taste ("less snark, more warmth")        -> kept as a standing lesson
- a question                                           -> answered
Everything kept here is fed to the designer on every run.
"""
import html
import re

from . import llm, telegram
from .common import http, log, now_iso

MAX_LESSONS = 40
TOPIC_BATCHES = 4        # a topic you send is explored in this many batches, then retired

URL = re.compile(r"https?://\S+")

SYSTEM = """You are Rory, the creative assistant for Daniel's Etsy print-on-demand shop.
You make t-shirt, hoodie, mug and sticker designs from trends. Daniel approves every design.
Speak plainly and warmly, briefly, like a capable colleague. No em dashes. No hype words."""

CLASSIFY = """Daniel just sent you this on Telegram:

\"\"\"{text}\"\"\"

What you already keep as standing design lessons:
{lessons}

Decide what it is and return JSON only:
{{"type": "topic" | "lesson" | "question" | "other",
  "topics": ["short topic phrases to explore in upcoming designs, if any"],
  "lessons": ["standing rules for future designs, phrased as instructions, if any"],
  "reply": "your short reply to Daniel (1-3 sentences). If it's a question, answer it."}}

- "topic": he wants designs about a theme, trend, audience or occasion.
- "lesson": feedback about taste, style, tone, fonts, colors, what to avoid or do more of.
- A message can contain both; fill both lists.
- Never accept a topic that would mean using a brand, trademark, real person, or politics;
  say so kindly in the reply and offer a safe angle instead."""

READ = """Daniel sent you this article to learn from. Pull out what is useful for designing
print-on-demand products that sell on Etsy (typography, layout, color, humor, niches, what
buyers want, what to avoid). Ignore anything unrelated.

Article ({url}):
\"\"\"{text}\"\"\"

Return JSON only:
{{"lessons": ["3 to 6 short, specific instructions you will follow from now on"],
  "topics": ["any niches or themes worth exploring, 0 to 3"],
  "reply": "2-3 sentences to Daniel: what you took from it."}}"""

MERGE = """Here are design lessons collected over time. Merge duplicates, drop anything
contradicted by a later lesson (later ones win), and keep the {n} most useful.
Return JSON only: {{"lessons": ["..."]}}

{lessons}"""


def _brief(state):
    b = state.setdefault("brief", {})
    b.setdefault("topics", [])
    b.setdefault("lessons", [])
    return b


def _page_text(url):
    r = http("GET", url, headers={"User-Agent": "Mozilla/5.0"}, retries=1, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"couldn't open the page ({r.status_code})")
    t = re.sub(r"(?is)<(script|style|nav|footer|header|noscript)[^>]*>.*?</\1>", " ", r.text)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    t = re.sub(r"\s+", " ", t).strip()
    return t[:15000]


def _add(b, topics=(), lessons=()):
    for t in topics:
        t = t.strip()
        if t and t.lower() not in [x["text"].lower() for x in b["topics"]]:
            b["topics"].append({"text": t, "added": now_iso(), "batches_left": TOPIC_BATCHES})
    for l in lessons:
        l = l.strip()
        if l and l not in b["lessons"]:
            b["lessons"].append(l)
    if len(b["lessons"]) > MAX_LESSONS:
        merged = llm.ask_json(SYSTEM, MERGE.format(n=25, lessons="\n".join(f"- {x}" for x in b["lessons"])))
        b["lessons"] = merged.get("lessons", b["lessons"])[:MAX_LESSONS]


def handle_message(text, state):
    b = _brief(state)
    urls = URL.findall(text)
    for url in urls[:3]:
        try:
            out = llm.ask_json(SYSTEM, READ.format(url=url, text=_page_text(url)))
            _add(b, out.get("topics", []), out.get("lessons", []))
            telegram.send("📚 " + out.get("reply", "Read it."))
        except Exception as e:
            log("  article failed:", e)
            telegram.send(f"I couldn't read that link ({str(e)[:120]}). If it's behind a login or paywall, "
                          "paste the key parts as a message instead.")
    rest = URL.sub("", text).strip()
    if rest and (not urls or len(rest) > 25):
        out = llm.ask_json(SYSTEM, CLASSIFY.format(
            text=rest, lessons="\n".join(f"- {x}" for x in b["lessons"]) or "(none yet)"))
        _add(b, out.get("topics", []), out.get("lessons", []))
        telegram.send(out.get("reply", "Got it."))


def prompt_block(state):
    """Text added to the designer's prompt on every batch."""
    b = _brief(state)
    parts = []
    live = [t for t in b["topics"] if t.get("batches_left", 0) > 0]
    if live:
        parts.append("Daniel asked you to explore these topics. Base at least one design in this batch on "
                     "one of them (rotate between them):\n" + "\n".join(f"- {t['text']}" for t in live))
    if b["lessons"]:
        parts.append("Daniel's standing design lessons. Follow them:\n" + "\n".join(f"- {x}" for x in b["lessons"]))
    designs = list(state["designs"].values())[-60:]
    yes = [" / ".join(d.get("lines") or [(d.get("illustration_prompt") or "")[:70]])
           for d in designs if d["status"] in ("approved", "approved_dry", "published")][-12:]
    no = [" / ".join(d.get("lines") or [(d.get("illustration_prompt") or "")[:70]])
          for d in designs if d["status"] == "rejected"][-12:]
    if yes or no:
        parts.append("Learn Daniel's taste from his recent decisions.\nApproved:\n" +
                     ("\n".join(f"- {x}" for x in yes) or "- (none yet)") + "\nSkipped:\n" +
                     ("\n".join(f"- {x}" for x in no) or "- (none yet)"))
    return "\n\n".join(parts)


def used_topics(state):
    for t in _brief(state)["topics"]:
        if t.get("batches_left", 0) > 0:
            t["batches_left"] -= 1


def list_topics(state):
    live = [t for t in _brief(state)["topics"] if t.get("batches_left", 0) > 0]
    if not live:
        return "No topics queued. Send me one anytime, like: look into winter hiking."
    return "Topics I'm exploring:\n" + "\n".join(f"{i + 1}. {t['text']}" for i, t in enumerate(live))


def list_lessons(state):
    ls = _brief(state)["lessons"]
    if not ls:
        return "No lessons yet. Send me feedback or an article to learn from."
    return "What I've learned:\n" + "\n".join(f"{i + 1}. {x}" for i, x in enumerate(ls))


def forget(state, what, n):
    b = _brief(state)
    key = "lessons" if what == "lesson" else "topics"
    items = b[key] if key == "lessons" else [t for t in b["topics"] if t.get("batches_left", 0) > 0]
    if 1 <= n <= len(items):
        gone = items[n - 1]
        if key == "lessons":
            b["lessons"].remove(gone)
            return f"Forgot: {gone}"
        gone["batches_left"] = 0
        return f"Dropped topic: {gone['text']}"
    return "I couldn't find that number. Send /lessons or /topics to see the list."
