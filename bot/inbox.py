"""Actions from Daniel's web dashboard (docs/index.html, served by GitHub Pages).

The dashboard can't talk to Rory directly, so each button press writes one small file to
inbox/ in the repo (using Daniel's own GitHub token, kept only in his browser). Rory's
listener checks inbox/ about every 30 seconds, and every run checks it at the start. Each
file is applied once, then deleted. The dashboard never touches state.json, so it can't
clash with Rory's own saves.
"""
import json
import subprocess
import traceback

from . import audit, designer, telegram
from .common import ROOT, log, now_iso

INBOX = ROOT / "inbox"


def pull():
    subprocess.run(["git", "pull", "--rebase", "--autostash", "-q"], cwd=ROOT, capture_output=True, text=True)


def _mark(d, text):
    """Keep the Telegram message in step with what was done on the dashboard."""
    mid = d.get("telegram_msg")
    if not mid:
        return
    try:
        (telegram.mark_text if d.get("kind") == "illustration" and not d.get("files") else telegram.mark)(mid, text)
    except Exception:
        pass


def apply(state, a):
    action, did = a.get("action"), a.get("id")
    d = state["designs"].get(did)
    if not d:
        return f"{did} not found"
    if action in ("approve", "reject"):
        if d["status"] != "pending" and not (action == "reject" and d["status"] == "idea"):
            return f"{did} is {d['status']}, not waiting"
        d["status"] = "approved" if action == "approve" else "rejected"
        d["decided"] = now_iso()
        audit.record(state, did, "approved" if action == "approve" else "skipped", via="dashboard")
        _mark(d, "✅ APPROVED on the dashboard" if action == "approve" else "❌ Skipped on the dashboard")
        return f"{did} {d['status']}"
    if action == "draw":
        if d["status"] != "idea":
            return f"{did} is {d['status']}, not an idea"
        d["status"] = "drawing"
        _mark(d, "🎨 Drawing it (asked on the dashboard)")
        try:
            designer.draw_idea(did, state)
        except Exception as e:
            d["status"] = "idea"
            raise e
        return f"{did} drawn"
    if action == "edit":
        if d["status"] not in ("pending", "idea"):
            return f"{did} is {d['status']}, can't edit"
        text = (a.get("text") or "").strip()
        if not text:
            return "empty edit"
        designer.edit_design(did, text, state, via="dashboard")
        return f"{did} edited"
    if action == "place":
        if d["status"] != "pending":
            return f"{did} is {d['status']}, can't move it"
        designer.reposition(did, state, move=float(a.get("move") or 0), center_h=bool(a.get("center_h")),
                            center_v=a.get("center_v"), reset=bool(a.get("reset")))
        return f"{did} repositioned"
    if action == "unskip":
        if d["status"] != "rejected":
            return f"{did} is {d['status']}"
        d["status"] = "idea" if d.get("kind") == "illustration" and not d.get("files") else "pending"
        audit.record(state, did, "restored", via="dashboard")
        return f"{did} back in the queue"
    return f"unknown action {action}"


def process(state):
    """Apply every waiting dashboard action. Returns how many were applied."""
    files = sorted(INBOX.glob("*.json")) if INBOX.exists() else []
    done = 0
    for f in files:
        try:
            a = json.loads(f.read_text())
            result = apply(state, a)
            log(f"  dashboard: {a.get('action')} {a.get('id')}: {result}")
            done += 1
        except Exception as e:
            log(f"  dashboard action {f.name} failed:", e)
            traceback.print_exc()
            telegram.send(f"⚠️ A dashboard action ({f.name}) failed: {str(e)[:200]}")
        f.unlink()
        subprocess.run(["git", "rm", "-q", "--cached", "--ignore-unmatch", str(f.relative_to(ROOT))],
                       cwd=ROOT, capture_output=True)
    if done:
        state.setdefault("dashboard", {})["last_applied"] = now_iso()
    return done
