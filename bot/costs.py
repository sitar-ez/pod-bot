"""Cost tracker: logs what each AI call actually costs, by day and by step.

Saved in state/costs.json (no buyer data). /cost on Telegram shows the totals.
Prices live in settings.py; the token counts come straight from each API response.
"""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import settings
from .common import ROOT, log

FILE = ROOT / "state" / "costs.json"
STAGE = {"name": "other"}   # set by run.stage() and the listener


def _today():
    return datetime.now(ZoneInfo(settings.WORK_TIMEZONE)).strftime("%Y-%m-%d")


def _load():
    try:
        return json.loads(FILE.read_text())
    except Exception:
        return {"days": {}}


def _add(service, usd, **counts):
    data = _load()
    day = data["days"].setdefault(_today(), {})
    row = day.setdefault(f"{service}: {STAGE['name']}", {"usd": 0.0})
    row["usd"] = round(row["usd"] + usd, 5)
    for k, v in counts.items():
        row[k] = row.get(k, 0) + v
    # keep about three months
    for old in sorted(data["days"])[:-95]:
        data["days"].pop(old)
    try:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        FILE.write_text(json.dumps(data, indent=1, sort_keys=True))
    except Exception as e:
        log("  cost log not written:", e)


def claude(msg):
    """Record one Anthropic response (tokens and any web searches)."""
    try:
        u = msg.usage
        tin = (u.input_tokens or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0) \
            + (getattr(u, "cache_read_input_tokens", 0) or 0)
        tout = u.output_tokens or 0
        stu = getattr(u, "server_tool_use", None)
        searches = (getattr(stu, "web_search_requests", 0) or 0) if stu else 0
        usd = (tin * settings.PRICE_CLAUDE_IN + tout * settings.PRICE_CLAUDE_OUT) / 1e6 \
            + searches * settings.PRICE_WEB_SEARCH
        _add("Claude", usd, calls=1, tokens_in=tin, tokens_out=tout, searches=searches)
    except Exception as e:
        log("  cost tracking skipped:", e)


def image(response_json):
    """Record one OpenAI image response."""
    try:
        u = response_json.get("usage") or {}
        tin, tout = u.get("input_tokens", 0) or 0, u.get("output_tokens", 0) or 0
        usd = (tin * settings.PRICE_IMAGE_TEXT_IN + tout * settings.PRICE_IMAGE_OUT) / 1e6
        _add("Images", usd, images=1, tokens_in=tin, tokens_out=tout, unpriced=0 if u else 1)
    except Exception as e:
        log("  cost tracking skipped:", e)


def report():
    """Plain-language summary for Telegram."""
    data = _load()["days"]
    today = _today()
    d0 = datetime.strptime(today, "%Y-%m-%d")
    week = {(d0 - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}
    month = today[:7]

    def total(days):
        rows = [r for d, day in data.items() if d in days for r in day.values()]
        return sum(r["usd"] for r in rows)

    t_today = total({today})
    t_week = total(week)
    t_month = total({d for d in data if d.startswith(month)})
    by_step = {}
    for d, day in data.items():
        if d in week:
            for k, r in day.items():
                by_step[k] = by_step.get(k, 0) + r["usd"]
    images = sum(r.get("images", 0) for d, day in data.items() if d in week for r in day.values())
    unpriced = sum(r.get("unpriced", 0) for d, day in data.items() if d in week for r in day.values())
    lines = [f"💵 AI costs\nToday: ${t_today:.2f}\nLast 7 days: ${t_week:.2f}\nThis month: ${t_month:.2f}",
             "", "Last 7 days by step:"]
    lines += [f"• {k}: ${v:.2f}" for k, v in sorted(by_step.items(), key=lambda kv: -kv[1])[:10]] or ["• nothing yet"]
    lines.append(f"\nImages drawn in 7 days: {images}")
    if unpriced:
        lines.append(f"({unpriced} image(s) came back without a token count, so they're not in the totals.)")
    lines.append("These are tracked from each API response. Your Anthropic and OpenAI billing pages "
                 "are the final word.")
    return "\n".join(lines)
