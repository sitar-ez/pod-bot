"""Shared helpers: state file, HTTP with retries, logging, paths."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "state" / "state.json"
DESIGNS_DIR = ROOT / "designs"
FONTS_DIR = ROOT / "fonts"


def log(*args):
    print(datetime.now().strftime("%H:%M:%S"), *args, flush=True)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def hours_since(iso):
    if not iso:
        return 1e9
    then = datetime.fromisoformat(iso)
    return (datetime.now(timezone.utc) - then).total_seconds() / 3600


def env(name, required=True, default=None):
    val = os.getenv(name, default)
    if required and not val:
        raise RuntimeError(f"Missing setting: {name}. Add it under GitHub > Settings > Secrets.")
    return val


# ---------------------------------------------------------------------------
# State: everything the bot needs to remember between runs
# ---------------------------------------------------------------------------
DEFAULT_STATE = {
    "designs": {},          # design_id -> record
    "orders": {},           # etsy receipt id -> record
    "telegram_offset": 0,
    "last_scout": None,
    "paused": False,
    "force_scout": False,
    "counts": {"text": 0, "illustration": 0},
    "cache": {},
    "last_error_ping": None,
}


def load_state():
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text())
        for k, v in DEFAULT_STATE.items():
            data.setdefault(k, v if not isinstance(v, (dict, list)) else type(v)(v))
        return data
    return json.loads(json.dumps(DEFAULT_STATE))


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))
    try:   # readable approval log (Etsy human-involvement record)
        from . import audit
        audit.write_markdown(state)
    except Exception as e:
        print("  approval log not written:", e)


# ---------------------------------------------------------------------------
# HTTP with polite retries (handles rate limits from Etsy and Printful)
# ---------------------------------------------------------------------------
def http(method, url, retries=4, **kw):
    kw.setdefault("timeout", 60)
    for attempt in range(retries + 1):
        r = requests.request(method, url, **kw)
        if r.status_code == 429 or r.status_code >= 500:
            wait = int(r.headers.get("Retry-After", 0) or 0) or (5 * (attempt + 1))
            log(f"  {r.status_code} from {url.split('?')[0]}, waiting {wait}s")
            time.sleep(min(wait, 90))
            continue
        return r
    return r


def raise_for(r, what):
    if r.status_code >= 400:
        raise RuntimeError(f"{what} failed ({r.status_code}): {r.text[:800]}")


def public_url(rel_path):
    """Public link to a file committed in this GitHub repo (Printful downloads from here)."""
    repo = os.getenv("GITHUB_REPOSITORY", "OWNER/REPO")
    branch = os.getenv("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{rel_path}"
