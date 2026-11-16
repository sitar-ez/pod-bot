"""Telegram: sends you designs with Approve / Skip buttons and reads your taps."""
import json

from .common import env, http, log


def _url(method):
    return f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/{method}"


def chat_id():
    return env("TELEGRAM_CHAT_ID")


def send(text):
    try:
        http("POST", _url("sendMessage"), data={"chat_id": chat_id(), "text": text[:4000],
                                                "disable_web_page_preview": "true"})
    except Exception as e:
        log("  telegram send failed:", e)


def send_design(jpg_bytes, caption, design_id):
    kb = {"inline_keyboard": [[
        {"text": "✅ Approve", "callback_data": f"approve:{design_id}"},
        {"text": "❌ Skip", "callback_data": f"reject:{design_id}"},
    ]]}
    r = http("POST", _url("sendPhoto"),
             data={"chat_id": chat_id(), "caption": caption[:1000], "reply_markup": json.dumps(kb)},
             files={"photo": ("preview.jpg", jpg_bytes, "image/jpeg")})
    if r.status_code >= 400:
        log("  telegram photo failed:", r.text[:300])
        return None
    return r.json()["result"]["message_id"]


def updates(offset):
    r = http("GET", _url("getUpdates"), params={"offset": offset, "timeout": 0})
    if r.status_code >= 400:
        log("  telegram getUpdates failed:", r.text[:300])
        return []
    return r.json().get("result", [])


def answer(callback_id, text):
    http("POST", _url("answerCallbackQuery"), data={"callback_query_id": callback_id, "text": text})


def mark(message_id, new_caption):
    http("POST", _url("editMessageCaption"),
         data={"chat_id": chat_id(), "message_id": message_id, "caption": new_caption[:1000]})
