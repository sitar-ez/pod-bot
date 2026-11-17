"""Dig deeper: turn generic ideas into specific, insider ones (Daniel, Nov 17, 2026).

"Garden tomato" isn't compelling. Daniel's rule: whenever an idea is generic, research the
subject and find something specific and true (an heirloom variety with a story, an
old-timer saying, a technique only growers know, a surprising fact) that the homestead
buyer would recognize and smile at.

Every new concept goes through here before the safety check. Claude judges each one and
rewrites only the generic ones, using web search.
"""
import json

from . import llm, settings
from .common import log

RULE = (
    "NEVER GENERIC (Daniel's rule): a design that just names the subject ('garden tomato', "
    "'I love my chickens', 'bees', 'fresh eggs') isn't compelling to our buyer. Every design needs one "
    "specific, true, insider detail about the subject: an heirloom variety and its story, an old-timer "
    "saying, a technique or chore only growers know, a regional tradition, a surprising fact. The buyer "
    "should recognize it and smile, as if a neighbor who also does this made the shirt."
)

PROMPT = """You are the second pass on print-on-demand design ideas for an Etsy shop whose buyers are
homesteaders, gardeners, canners and backyard-chicken keepers (mostly women 30 to 65, practical, warm,
a little wry).

{rule}

Here are the ideas:
{concepts}
{note}
For EACH idea, decide: is it generic? It's generic if a stranger could have guessed it from the topic
word alone, or if it would fit on any mass-market garden or farm shirt.

- Not generic: return it unchanged, with "deepened": false.
- Generic: use web search to research the subject. Look for the specific, true, delightful details
  insiders know: named heirloom varieties and how they got their names, seed-saving lore, old
  almanac or farm sayings, the chores and small rituals of doing it, pests and mishaps everyone
  shares, surprising history or science. Pick ONE detail that is true (confirmed by a reliable source)
  and would make the buyer grin. Rebuild the idea around it, keeping the same "kind" (text or
  illustration), products, garment, style and layout fields. Rewrite the lines or illustration_prompt,
  titles, tags, description, trend_signal and why_it_sells to match. Set "deepened": true,
  "insider_fact": one plain sentence on the detail, and "source": the URL that confirms it.

Hard rules for rewrites:
- No real people's names (no breeders, no celebrities). Variety names that are common, public
  names sold by many seed companies are fine. No brand names or trademarks. No quotes, lyrics or
  religious references.
- The phrase must make sense to a stranger who doesn't know the fact, and be a little funnier or
  warmer to the one who does.
- For illustrations, the prompt must describe one clear printable image (no tiny paragraphs of text).
  Any words in the image must be short and spelled out exactly.

Return JSON only: {{"concepts": [ ...every idea, in the same order, full objects... ]}}"""


def _search_json(prompt, max_searches):
    client = llm.client()
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}]
    messages = [{"role": "user", "content": prompt}]
    msg = None
    for _ in range(4):
        msg = client.messages.create(model=settings.CLAUDE_MODEL, max_tokens=8000,
                                     messages=messages, tools=tools)
        if msg.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": msg.content}]
    text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
    return llm.parse_json(text)


def deepen(concepts, note=None):
    """Return the concepts with generic ones rewritten around a researched insider detail.
    On any failure, returns the originals so a run never stalls."""
    if not concepts:
        return concepts
    try:
        out = _search_json(PROMPT.format(
            rule=RULE, concepts=json.dumps(concepts, indent=1),
            note=f"\nDaniel's note about this idea: {note}\n(Treat it as generic and dig deeper.)\n" if note else "",
        ), max_searches=3 * len(concepts))
        new = out.get("concepts") or []
        if len(new) != len(concepts):
            log(f"  dig deeper returned {len(new)} of {len(concepts)} ideas; keeping originals")
            return concepts
        for old, c in zip(concepts, new):
            c["kind"] = old.get("kind")
            if c.get("deepened"):
                log(f"  dug deeper: {c.get('insider_fact', '')[:120]}")
        return new
    except Exception as e:
        log("  dig deeper failed, keeping originals:", e)
        return concepts
