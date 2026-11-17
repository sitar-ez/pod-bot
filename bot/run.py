"""
The main loop. GitHub wakes this every 20 minutes; it works 9am-5pm Eastern, every 40 minutes.

1. Read your Telegram taps (approve / skip) and commands
2. Publish anything you approved
3. Send new Etsy orders to Printful, and tracking back to Etsy
4. Scout trends and make 2 new designs
"""
import os
import traceback

from . import brief, designer, personalize, products, study, publisher, settings, scout, telegram, fulfillment
from datetime import datetime
from zoneinfo import ZoneInfo

from .common import hours_since, http, load_state, log, now_iso, public_url, save_state

HELP = ("Talk to me like a colleague. Send a trend to explore, an article link to learn from, "
        "or feedback on my designs, and I'll use it from now on.\n\n"
        "Commands:\n/status  what's waiting and what's live\n/more  extra batch on the next run\n"
        "/topics  trends you've asked me to explore\n/lessons  what I've learned from you\n"
        "/forget 3  drop lesson number 3\n/drop 2  drop topic number 2\n"
        "To change a design: tap ✏️ Edit and type the change, or reply to the design.\n"
        "/study  extra study session (or /study color theory for a topic you choose)\n"
        "/pause  stop making designs\n/resume  start again\n/help  this list")


def handle_telegram(state, ups=None):
    me = str(telegram.chat_id())
    for u in (ups if ups is not None else telegram.updates(state["telegram_offset"])):
        state["telegram_offset"] = u["update_id"] + 1
        cb = u.get("callback_query")
        msg = u.get("message")
        if cb and str(cb["message"]["chat"]["id"]) == me:
            action, did = cb["data"].split(":", 1)
            if action in ("order_ok", "order_hold"):
                ans = personalize.handle_callback(action, did, state)
                try:
                    telegram.answer(cb["id"], ans or "Got it")
                except Exception:
                    pass
                continue
            if action in ("product_ok", "product_adjust"):
                ans = products.handle_callback(action, did, state)
                try:
                    telegram.answer(cb["id"], ans or "Got it")
                except Exception:
                    pass
                continue
            d = state["designs"].get(did)
            if not d or d["status"] != "pending":
                continue
            if action == "edit":
                state["editing"] = {"id": did, "at": now_iso()}
                telegram.mark(cb["message"]["message_id"],
                              "✏️ EDITING: tell me what to change\n\n" + cb["message"].get("caption", ""))
                telegram.send(f"What should I change about {did}? Just type it, for example: "
                              "\"make it smaller and lower on the chest\", \"use a bolder font\", "
                              "\"change the words to ...\", \"make the cat look happier\".")
                continue
            d["status"] = "approved" if action == "approve" else "rejected"
            d["decided"] = now_iso()
            try:
                telegram.answer(cb["id"], "✅ Approved" if action == "approve" else "❌ Skipped")
            except Exception:
                pass
            old = cb["message"].get("caption", "")
            tag = "✅ APPROVED, it goes to Etsy on the next run" if action == "approve" else "❌ Skipped"
            telegram.mark(cb["message"]["message_id"], f"{tag}\n\n{old}")
            log(f"  {did}: {d['status']}")
        elif msg and str(msg["chat"]["id"]) == me:
            text = (msg.get("text") or "").strip().lower()
            if text.startswith("/pause"):
                state["paused"] = True
                telegram.send("Paused. I'll still handle orders and approvals. /resume to restart designs.")
            elif text.startswith("/resume"):
                state["paused"] = False
                telegram.send("Back on. Next batch arrives on schedule.")
            elif text.startswith("/more"):
                state["force_scout"] = True
                telegram.send("A fresh batch is coming on the next run.")
            elif text.startswith("/status"):
                ds = state["designs"].values()
                count = lambda s: sum(1 for d in ds if d["status"] == s)
                telegram.send(
                    f"Waiting on you: {count('pending')}\nApproved, publishing: {count('approved')}\n"
                    f"Live: {count('published')}\nSkipped: {count('rejected')}\n"
                    f"Orders handled: {sum(1 for o in state['orders'].values() if o.get('status') in ('sent', 'shipped'))}\n"
                    f"Dry run: {'ON' if settings.DRY_RUN else 'off'} · Designs paused: {'yes' if state['paused'] else 'no'}")
            elif text.startswith("/study"):
                topic = (msg.get("text") or "")[6:].strip()
                state["study_force"] = topic or True
                telegram.send(f"I'll study {'that' if topic else 'my next curriculum topic'} on my next run.")
            elif text.startswith("/topics"):
                telegram.send(brief.list_topics(state))
            elif text.startswith("/lessons"):
                telegram.send(brief.list_lessons(state))
            elif text.startswith("/forget") or text.startswith("/drop"):
                num = "".join(ch for ch in text if ch.isdigit())
                telegram.send(brief.forget(state, "lesson" if text.startswith("/forget") else "topic",
                                           int(num) if num else 0))
            elif text.startswith("/help") or text.startswith("/start") or not text:
                telegram.send(HELP)
            elif state.get("editing_product") and hours_since(state["editing_product"].get("at")) < 3 \
                    and not text.startswith("/"):
                ep = state.pop("editing_product")
                try:
                    products.handle_adjust(ep["key"], msg.get("text") or "", state)
                except Exception as e:
                    log("  product adjust failed:", e)
                    telegram.send(f"Sorry, I couldn't apply that: {str(e)[:200]}")
            else:
                replied = (msg.get("reply_to_message") or {}).get("message_id")
                target = next((k for k, d in state["designs"].items()
                               if replied and d.get("telegram_msg") == replied and d["status"] == "pending"), None)
                ed = state.pop("editing", None)
                if not target and isinstance(ed, dict) and hours_since(ed.get("at")) < 3:
                    target = ed["id"]
                if target and state["designs"].get(target, {}).get("status") == "pending":
                    state.pop("editing", None)
                    try:
                        designer.edit_design(target, msg.get("text") or "", state)
                    except Exception as e:
                        log("  edit failed:", e)
                        traceback.print_exc()
                        telegram.send(f"Sorry, the edit to {target} failed: {str(e)[:200]}")
                    continue
                try:
                    brief.handle_message(msg.get("text") or "", state)
                except Exception as e:
                    log("  message handling failed:", e)
                    telegram.send("Sorry, I hit a snag reading that. Try again in a bit.")


def files_are_public(d):
    first = next(iter(next(iter(d["files"].values())).values()))
    return http("HEAD", public_url(first), retries=0).status_code == 200


def stage(name, fn, state):
    try:
        log(f"== {name}")
        fn()
    except Exception as e:
        log(f"!! {name} failed: {e}")
        traceback.print_exc()
        if hours_since(state.get("last_error_ping")) > 3:
            telegram.send(f"⚠️ The bot hit a problem while trying to {name}:\n{str(e)[:600]}\n"
                          "It will keep trying. Details are in the GitHub Actions log.")
            state["last_error_ping"] = now_iso()


def in_work_window(state):
    """GitHub wakes the bot every 20 minutes; it only works 9-5 Eastern, every 40 minutes."""
    if os.getenv("FORCE_RUN") == "true":
        return True
    local = datetime.now(ZoneInfo(settings.WORK_TIMEZONE))
    if not (settings.WORK_START_HOUR <= local.hour < settings.WORK_END_HOUR):
        log(f"  outside working hours ({local:%H:%M} {settings.WORK_TIMEZONE}), sleeping")
        return False
    if hours_since(state.get("last_run")) * 60 < settings.RUN_EVERY_MINUTES - 3:
        log("  ran less than 40 minutes ago, sleeping")
        return False
    return True


def main():
    state = load_state()
    if state.get("telegram_chat_id"):
        telegram._found["id"] = state["telegram_chat_id"]
    if not in_work_window(state):
        return
    state["last_run"] = now_iso()
    etsy_box = {}

    def etsy():
        if "e" not in etsy_box:
            from .etsy import Etsy
            etsy_box["e"] = Etsy()
        return etsy_box["e"]

    def read_telegram():
        first_time = not state.get("telegram_chat_id") and not os.getenv("TELEGRAM_CHAT_ID")
        state["telegram_chat_id"] = str(telegram.chat_id())
        if first_time:
            telegram.send("👋 Connected! I'll send designs here for you to approve. " + HELP)
        handle_telegram(state)

    stage("read Telegram", read_telegram, state)
    save_state(state)

    def publish_approved():
        for d in list(state["designs"].values()):
            ready = ("approved",) if settings.DRY_RUN else ("approved", "approved_dry")
            if d["status"] not in ready:
                continue
            if not files_are_public(d):
                log(f"  {d['id']}: files not public yet, will publish next run")
                continue
            publisher.publish(d, etsy(), state)
            save_state(state)

    stage("publish approved designs", publish_approved, state)

    def refresh_live():
        for did, keys in list(state.get("refresh_listings", {}).items()):
            d = state["designs"].get(did)
            if d and files_are_public(d):
                publisher.refresh_photos(d, keys, etsy(), state)
                state["refresh_listings"].pop(did, None)
                save_state(state)
    def policies_live():
        for d in state["designs"].values():
            if d["status"] == "published" and not d.get("policy_v1"):
                publisher.update_live_policies(d, etsy(), state)
                d["policy_v1"] = True
                save_state(state)
    if not settings.DRY_RUN:
        stage("set return policy on live listings", policies_live, state)

    if state.get("refresh_listings") and not settings.DRY_RUN:
        stage("update live listing photos", refresh_live, state)

    has_etsy = bool(os.getenv("ETSY_REFRESH_TOKEN"))
    if has_etsy:
        stage("send new orders to Printful", lambda: fulfillment.send_new_orders(etsy(), state), state)
        save_state(state)
        stage("sync tracking to Etsy", lambda: fulfillment.sync_tracking(etsy(), state), state)
        save_state(state)

    if state.get("replace_pending"):
        def replace_pending():
            from .common import DESIGNS_DIR
            for did, d in list(state["designs"].items()):
                c = d.get("concept")
                if d["status"] != "pending" or not c:
                    continue
                c = dict(c)
                c["layout"] = {**(c.get("layout") or {}), "top": None}
                master = DESIGNS_DIR / did / "master.png"
                reuse = str(master) if d["kind"] == "illustration" and master.exists() else None
                designer.make_design(c, state, parent=did, reuse_master=reuse)
                d["status"] = "replaced"
                save_state(state)
            state["replace_pending"] = False
            telegram.send("📐 I re-placed the designs that were waiting on you using your new placement rule "
                          "(big designs about 5 inches below the collar, small ones about 9). The updated "
                          "versions are above; the old ones are retired.")
        stage("re-place pending designs", replace_pending, state)
        save_state(state)

    stage("check new products", lambda: products.run_checks(state), state)
    save_state(state)

    if study.due(state):
        stage("study design", lambda: study.study(state), state)
        save_state(state)

    pending = sum(1 for d in state["designs"].values() if d["status"] == "pending")
    if not state["paused"] and pending < settings.MAX_PENDING_APPROVALS:
        def batch():
            concepts = scout.scout(state)
            state["last_scout"] = now_iso()
            state["force_scout"] = False
            made = 0
            for c in concepts:
                try:
                    designer.make_design(c, state)
                    made += 1
                    save_state(state)
                except Exception as e:
                    log(f"  design failed: {e}")
                    traceback.print_exc()
            if made:
                telegram.send(f"🎨 {made} new design(s) above. Tap Approve or Skip on each. "
                              "Taps are picked up on the next run (every 40 minutes, 9am to 5pm).")
        stage("make new designs", batch, state)
    elif pending >= settings.MAX_PENDING_APPROVALS:
        log("  too many designs waiting for approval; not making more")

    save_state(state)
    log("done")


if __name__ == "__main__":
    main()
