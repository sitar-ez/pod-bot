"""Telegram: sends you designs with Approve / Skip buttons and reads your taps."""
import json
import os

from .common import env, http, log


def _url(method):
    return f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/{method}"


_found = {"id": None}


def chat_id():
    """Your chat ID. If it isn't set in GitHub, the bot learns it from the first
    message you send your bot, and remembers it."""
    cid = os.getenv("TELEGRAM_CHAT_ID") or _found["id"]
    if cid:
        return cid
    for u in updates(0):
        msg = u.get("message") or (u.get("callback_query") or {}).get("message")
        if msg and msg.get("chat", {}).get("type") == "private":
            _found["id"] = str(msg["chat"]["id"])
            log(f"  found your Telegram chat ({_found['id']})")
            return _found["id"]
    raise RuntimeError("Send your Telegram bot a message (any word), then run the bot again.")


def send(text):
    try:
        r = http("POST", _url("sendMessage"), data={"chat_id": chat_id(), "text": text[:4000],
                                                    "disable_web_page_preview": "true"})
        if r.status_code >= 400:
            log(f"  telegram send failed ({r.status_code}): {r.text[:300]}")
        else:
            log(f"  telegram: sent \"{text[:50]}\"")
    except Exception as e:
        log("  telegram send failed:", e)


def send_design(jpg_bytes, caption, design_id):
    kb = {"inline_keyboard": [[
        {"text": "✅ Approve", "callback_data": f"approve:{design_id}"},
        {"text": "✏️ Edit", "callback_data": f"edit:{design_id}"},
        {"text": "❌ Skip", "callback_data": f"reject:{design_id}"},
    ]]}
    r = http("POST", _url("sendPhoto"),
             data={"chat_id": chat_id(), "caption": caption[:1000], "reply_markup": json.dumps(kb)},
             files={"photo": ("preview.jpg", jpg_bytes, "image/jpeg")})
    if r.status_code >= 400:
        log("  telegram photo failed:", r.text[:300])
        return None
    return r.json()["result"]["message_id"]


def updates(offset, wait=0):
    """wait > 0 long-polls: Telegram holds the request open until something arrives."""
    r = http("GET", _url("getUpdates"), params={"offset": offset, "timeout": wait,
                                                "allowed_updates": json.dumps(["message", "callback_query"])},
             timeout=wait + 30)
    if r.status_code >= 400:
        log("  telegram getUpdates failed:", r.text[:300])
        return []
    res = r.json().get("result", [])
    kinds = [("tap" if "callback_query" in u else "message" if "message" in u else "other") for u in res]
    if res or not wait:
        log(f"  telegram: {len(res)} new update(s) {kinds}")
    if not res and not wait:
        try:
            info = http("GET", _url("getWebhookInfo"), retries=0).json().get("result", {})
            log(f"  telegram check: pending={info.get('pending_update_count')} webhook={info.get('url') or 'none'} "
                f"last_error={info.get('last_error_message')}")
        except Exception as e:
            log("  telegram check failed:", e)
    return res


def answer(callback_id, text):
    http("POST", _url("answerCallbackQuery"), data={"callback_query_id": callback_id, "text": text})


def mark(message_id, new_caption):
    http("POST", _url("editMessageCaption"),
         data={"chat_id": chat_id(), "message_id": message_id, "caption": new_caption[:1000]})


def send_photo_url(url, caption=""):
    try:
        http("POST", _url("sendPhoto"), data={"chat_id": chat_id(), "photo": url, "caption": caption[:1000]})
    except Exception as e:
        log("  telegram photo failed:", e)


def send_buttons(text, buttons):
    kb = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in buttons]]}
    r = http("POST", _url("sendMessage"), data={"chat_id": chat_id(), "text": text[:4000],
                                                "reply_markup": json.dumps(kb)})
    try:
        return r.json()["result"]["message_id"]
    except Exception:
        return None


def mark_text(message_id, new_text):
    """Rewrite a text message (used on idea cards, which have no photo caption)."""
    try:
        http("POST", _url("editMessageText"),
             data={"chat_id": chat_id(), "message_id": message_id, "text": new_text[:4000]})
    except Exception as e:
        log("  telegram edit failed:", e)


def send_photo_bytes(jpg, caption=""):
    try:
        http("POST", _url("sendPhoto"), data={"chat_id": chat_id(), "caption": caption[:1000]},
             files={"photo": ("proof.jpg", jpg, "image/jpeg")})
    except Exception as e:
        log("  telegram photo failed:", e)
