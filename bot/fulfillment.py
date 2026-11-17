"""Fulfillment: paid Etsy orders -> Printful, and Printful tracking -> Etsy."""
import re

from . import personalize, printful, settings, telegram
from .common import log, now_iso, public_url

SKU = re.compile(r"^PB-(d\d{6}-\d{2})-(\d+)$")


def money(m):
    try:
        return f"{m['amount'] / m['divisor']:.2f}"
    except Exception:
        return None


def send_new_orders(etsy, state):
    for r in etsy.unshipped_receipts():
        rid = str(r["receipt_id"])
        o = state["orders"].get(rid)
        if o and o.get("status") != "approved":
            continue   # already sent, not ours, waiting for Daniel's OK, or held
        items, personal = [], []
        for t in r.get("transactions", []):
            m = SKU.match(t.get("sku") or "")
            if not m:
                continue
            did, vid = m.groups()
            d = state["designs"].get(did)
            if not d:
                continue
            key = next((k for k, files in d["files"].items() if vid in files), None)
            if not key:
                continue
            placement = printful.resolve_product(key, state).get("placement", settings.PRODUCTS[key]["placement"])
            file_url = public_url(d["files"][key][vid])
            if d.get("personalize"):
                tid = str(t.get("transaction_id"))
                done = (o or {}).get("files", {}).get(tid)
                if done:                      # approved earlier: use the proofed file
                    file_url = public_url(done)
                else:
                    name, warn = personalize.clean(personalize.buyer_name(t))
                    name = name or d["personalize"]["sample"]
                    img, rel, v = personalize.render_print(d, key, vid, name, state, f"{rid}_{tid}")
                    personal.append({"tid": tid, "file": rel, "name": name, "warnings": warn,
                                     "product": settings.PRODUCTS[key]["label"],
                                     "proof": personalize.proof_jpg(img, v, key)})
            items.append({
                "variant_id": int(vid), "quantity": t["quantity"],
                "files": [{"type": placement, "url": file_url}],
                "retail_price": money(t.get("price", {})),
                "name": t.get("title", "")[:100],
            })
        if not items:
            state["orders"][rid] = {"status": "not_ours", "seen": now_iso()}
            continue
        if personal:   # new personalized order: wait for Daniel's OK (files are saved to GitHub meanwhile)
            state["orders"][rid] = {"status": "awaiting_ok", "seen": now_iso(),
                                    "files": {p["tid"]: p["file"] for p in personal}}
            personalize.request_ok(rid, personal, state)
            log(f"  order {rid}: personalized, waiting for Daniel's OK")
            continue
        recipient = {
            "name": r.get("name"), "address1": r.get("first_line"), "address2": r.get("second_line") or "",
            "city": r.get("city"), "state_code": r.get("state") or "", "country_code": r.get("country_iso"),
            "zip": r.get("zip"),
        }
        if settings.DRY_RUN:
            log(f"  [dry run] would send Etsy order {rid} to Printful ({len(items)} items)")
            continue
        order = printful.create_order(f"etsy-{rid}", recipient, items, settings.AUTO_CONFIRM_ORDERS)
        state["orders"][rid] = {"status": "sent", "printful_id": order["id"], "created": now_iso()}
        how = "sent to production" if settings.AUTO_CONFIRM_ORDERS else "saved as a Printful draft for you to confirm"
        telegram.send(f"💰 Etsy order #{rid}: {sum(i['quantity'] for i in items)} item(s), {how}.")
        log(f"  order {rid} -> Printful #{order['id']}")


def sync_tracking(etsy, state):
    for rid, o in state["orders"].items():
        if o.get("status") != "sent":
            continue
        order = printful.get_order(f"etsy-{rid}")
        if not order:
            continue
        ships = [s for s in order.get("shipments", []) if s.get("tracking_number")]
        if not ships:
            if order.get("status") in ("canceled", "failed"):
                o["status"] = order["status"]
                telegram.send(f"⚠️ Printful order for Etsy #{rid} is {order['status']}. Please check Printful.")
            continue
        s = ships[0]
        carrier = (s.get("carrier") or "other").lower().replace(" ", "-")
        if settings.DRY_RUN:
            continue
        etsy.add_tracking(rid, s["tracking_number"], carrier)
        o["status"] = "shipped"
        o["shipped"] = now_iso()
        telegram.send(f"📦 Etsy order #{rid} shipped ({s.get('carrier')} {s['tracking_number']}).")
