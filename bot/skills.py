"""
Agent skills Rory reads before designing. Each skill is a folder in /skills with a
SKILL.md (the open Agent Skills format). Installed:
- canvas-design (Anthropic, Apache 2.0): design-philosophy-first approach, craftsmanship, originality
- theme-factory (Anthropic, Apache 2.0): 10 tested color palettes
Rory makes apparel, not posters or slide decks, so each skill comes with a short note on
how to apply it here. To add a skill: put its folder in /skills and add a note below.
"""
import re

from .common import ROOT

SKILLS_DIR = ROOT / "skills"

HOW_TO_APPLY = {
    "canvas-design": (
        "Use this skill's thinking, not its file steps. Before each design, settle a one-line design "
        "philosophy (the feeling and visual language) and let every choice serve it. Aim for crafted, "
        "intentional work, limited cohesive palettes, nothing crowded, generous margins, and never copy an "
        "existing artist. It matters most for ILLUSTRATIONS: put the philosophy into the illustration_prompt. "
        "For apparel, readability beats subtlety: text must read from across a room, so ignore the advice "
        "about thin fonts and tiny labels. You do not write .md, .pdf or .png files; your output is still the JSON asked for."),
    "theme-factory": (
        "Use these palettes as tested starting points for ink colors and illustration palettes. Ignore the "
        "font names and the slide-deck steps. Check contrast against the garment color."),
}


def _strip_frontmatter(text):
    return re.sub(r"^---.*?---\s*", "", text, flags=re.S).strip()


def prompt_block():
    if not SKILLS_DIR.exists():
        return ""
    parts = []
    for folder in sorted(p for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").exists()):
        name = folder.name
        if name == "theme-factory":
            themes = []
            for t in sorted((folder / "themes").glob("*.md")):
                txt = t.read_text()
                title = txt.splitlines()[0].lstrip("# ").strip()
                colors = re.findall(r"\*\*(.+?)\*\*: `(#[0-9a-fA-F]{6})`", txt)
                best = re.search(r"## Best Used For\s+(.+)", txt)
                themes.append(f"- {title}: " + ", ".join(f"{n} {h}" for n, h in colors) +
                              (f" (suits: {best.group(1).strip()})" if best else ""))
            body = "Palettes:\n" + "\n".join(themes)
        else:
            body = _strip_frontmatter((folder / "SKILL.md").read_text())
        note = HOW_TO_APPLY.get(name, "Apply what's relevant to apparel design; your output is still the JSON asked for.")
        parts.append(f"<skill name=\"{name}\">\nHOW TO APPLY HERE: {note}\n\n{body}\n</skill>")
    if not parts:
        return ""
    return "Design skills installed for you. Read them and apply them as described:\n\n" + "\n\n".join(parts)
