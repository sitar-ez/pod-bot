"""
Shop direction, from the approved customer-avatar brief (Nov 17, 2026).
Focus: homemade, food and craft, feel-good homestead designs. Design for moms and
grandmas; write listings for the daughters and grandkids buying gifts for them.
"""
import re

THEMES = [
    "Jam, preserves, canning season and proud pantry shelves (the 'Small Batch' family)",
    "Backyard hens and eggs: named chickens, egg money, coop life",
    "Garden harvest: tomatoes, zucchini overload, seed packets",
    "Sourdough and baking from scratch",
    "Grandma's kitchen: recipe cards, made with love, the family kitchen",
    "Seasonal: right now that means Christmas baking and cozy kitchen gifts "
    "(spring: Mother's Day garden; late summer: canning season)",
]

# Rollout order for family names (add slowly: at most about 1 in 5 designs)
NAMES = ["Nana", "Mimi", "Mamaw", "Meemaw", "Grammy", "Gigi", "Mom-Mom", "Mama", "Granny", "Oma"]
NAME_SHARE = 0.20
NAME_RE = re.compile(r"\b(" + "|".join(re.escape(n) for n in NAMES + ["Momma", "Mom", "Grandma"]) + r")\b", re.I)

AVATARS = """WHO YOU DESIGN FOR
1. "Jenny," the kitchen-table homesteader (buys for herself): 38 to 55, married with kids, a quarter acre
   or a few acres. Keeps a vegetable garden, cans tomatoes and jam in August, keeps 6 to 10 named hens,
   has had a sourdough starter since 2020, sews or mends. Proud, warm, self-aware, a little tired.
   Her jokes: too many zucchini, chickens running the house, a pantry shelf she's proud of. Never snarky.
   She'd say: "Finally, a shirt that's actually me."
2. "Katie," the grateful daughter (buys for mom or grandma): 26 to 44, Etsy's core shopper. Buys for the
   family's jam maker, gardener or quilter (55 to 80). Christmas, Mother's Day, birthdays, a new grandbaby.
   Wants a gift that shows she noticed who mom is. Sentimental, a bit funny, never insulting about age.
   She'd say: "This is SO Grandma. She's going to cry."
Design for Jenny and for Katie's mom. Write titles and tags for the person buying the gift."""

VOICE = """VOICE AND LOOK
- Warm, gentle humor. Proud, never mocking. No jokes about age, weight, or being "old".
- No faith or religious designs. No politics.
- Vintage label, seed packet and recipe card styles.
- Muted natural palette: tomato red #B5432F, butter yellow #E8C766, sage #8A9A78, cream #F3EBD8,
  berry #7A2E3E, deep brown #3B2A20. Pick inks from these (and close cousins).
- Favor serif and script/handwriting font pairings; use stark sans-serifs sparingly.
- Simple and readable at arm's length.
- Never reuse "Homesteading Is My Jam" (an existing listing)."""

BUYER_TAGS = ("gift for grandma, nana gift, grandma gift, homestead mama, canning gift, "
              "chicken lover gift, gift for mom, cottagecore, homesteading, farmhouse kitchen")

RELIGIOUS = re.compile(r"\b(jesus|christ|god|lord|blessed|blessing|bless|scripture|bible|prayer|pray|praying|"
                       r"faith|church|amen|gospel|psalm|holy|heaven)\b", re.I)


def has_name(text):
    return bool(NAME_RE.search(text or ""))


def batch_plan(state, n_text, n_ill):
    """Which theme(s) this batch covers and whether one design should carry a family name."""
    i = state.get("theme_index", 0)
    themes = [THEMES[(i + k) % len(THEMES)] for k in range(max(1, n_text + n_ill))]
    state["theme_index"] = i + 1
    recent = [d for d in list(state["designs"].values())[-10:]]
    named = sum(1 for d in recent if has_name(" ".join(d.get("lines") or [])))
    name = None
    if recent and named / max(1, len(recent)) < NAME_SHARE:
        k = state.get("name_index", 0)
        name = NAMES[k % len(NAMES)]
        state["name_index"] = k + 1
    elif not recent:
        name = None
    lines = ["THIS BATCH"]
    for k, t in enumerate(themes):
        lines.append(f"- Design {k + 1}: {t}")
    if name:
        lines.append(f"- Exactly one TEXT design in this batch uses the family name \"{name}\", paired with its "
                     f"homestead theme (like \"{name}'s Small Batch\" or \"{name}'s Garden\"). Never a name-only "
                     f"design. Put \"{name}\" and \"{name.lower()} gift\" in its title and tags.")
    else:
        lines.append("- Don't use mom or grandma names in this batch.")
    lines.append("- Use the news below only for angles that fit these themes (egg prices, canning season, "
                 "a garden or baking trend). Ignore everything else in the news.")
    return "\n".join(lines)


def prompt_block(state, n_text, n_ill, comfort_colors=False):
    tags = (f"TITLE AND TAG PHRASES to draw from: {BUYER_TAGS}, plus the specific name on the design.")
    if comfort_colors:
        tags += " For tees, include \"Comfort Colors\" in the title and tags."
    return "\n\n".join([AVATARS, VOICE, batch_plan(state, n_text, n_ill), tags])
