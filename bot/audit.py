"""Approval log: a record of the human decisions behind every design and listing.

Etsy's Oct 22, 2026 rules ban bot-generated listings "without any human involvement".
This log is the proof that Daniel reviewed, edited and approved each design himself.
Each event goes on the design (design["history"], saved in state/state.json). A readable
copy is rebuilt at state/APPROVALS.md every time state is saved.
No buyer data is ever written here.
"""
from pathlib import Path

from .common import now_iso

ROOT = Path(__file__).resolve().parent.parent
MD = ROOT / "state" / "APPROVALS.md"
PHOTO_BASIS = ("Printful mockups of Daniel's original design on a standard base product "
               "(Etsy's production-partner stock-mockup exception)")

LABELS = {
    "proposed": "💡 Rory proposed",
    "edit_requested": "✏️ Daniel asked for changes",
    "revised": "🔁 Revised version made",
    "draw_requested": "🎨 Daniel asked Rory to draw the idea",
    "drawn": "🖼️ Rory drew it",
    "approved": "✅ Daniel approved",
    "skipped": "❌ Daniel skipped",
    "published": "🛍️ Listed on Etsy",
    "replaced": "↪️ Replaced by a revision",
}


def record(state, did, event, note=None, via="Telegram", at=None, **extra):
    d = state["designs"].get(did)
    entry = {"at": at or now_iso(), "design": did, "event": event, "by": _who(event), "via": via}
    if note:
        entry["note"] = str(note)[:500]
    entry.update({k: v for k, v in extra.items() if v is not None})
    if d is not None:
        d.setdefault("history", []).append({k: v for k, v in entry.items() if k != "design"})
    return entry


def _who(event):
    return "Rory (bot)" if event in ("proposed", "revised", "published", "replaced", "drawn") else "Daniel"


def backfill(state):
    """Give older designs a history from the timestamps they already carry (runs once each)."""
    for did, d in state["designs"].items():
        if d.get("history"):
            continue
        record(state, did, "proposed", via="automatic", at=d.get("created"),
               note=f"revision of {d['parent']}" if d.get("parent") else d.get("trend_signal"))
        if d.get("status") in ("approved", "approved_dry", "published"):
            record(state, did, "approved", at=d.get("decided") or d.get("created"), note="(from earlier records)")
        elif d.get("status") == "rejected":
            record(state, did, "skipped", at=d.get("decided") or d.get("created"), note="(from earlier records)")
        if d.get("status") == "published":
            record(state, did, "published", via="automatic", at=d.get("published"),
                   listings=d.get("listings"), photos=PHOTO_BASIS)


def write_markdown(state):
    """Readable log, newest designs first. Only designs Daniel has acted on, plus what's waiting."""
    rows = sorted(state["designs"].items(), key=lambda kv: kv[1].get("created") or "", reverse=True)
    out = ["# Approval log", "",
           "Every design Rory proposes waits for Daniel's decision on Telegram. Nothing is listed on "
           "Etsy without his approval. This file is rebuilt automatically on every run.", "",
           f"Photo basis for every listing: {PHOTO_BASIS}.", ""]
    for did, d in rows:
        hist = d.get("history") or []
        if not hist:
            continue
        name = " / ".join(d.get("lines") or []) or (d.get("titles") or {}).get("tee", "")[:60]
        out.append(f"## {did} · {d.get('status')} · {name}")
        for h in hist:
            line = f"- {h['at'][:16].replace('T', ' ')} UTC · {LABELS.get(h['event'], h['event'])} ({h['by']}, {h['via']})"
            if h.get("note"):
                line += f": {h['note']}"
            if h.get("listings"):
                line += " · " + ", ".join(f"{k} etsy.com/listing/{v}" for k, v in h["listings"].items())
            out.append(line)
        out.append("")
    MD.write_text("\n".join(out))
