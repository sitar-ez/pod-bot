"""Printful: catalog lookups, print areas, mockups and orders."""
import os
import re
import time

from . import settings
from .common import env, http, log, raise_for

BASE = "https://api.printful.com"


def _headers():
    h = {"Authorization": f"Bearer {env('PRINTFUL_TOKEN')}"}
    store = os.getenv("PRINTFUL_STORE_ID")
    if store:
        h["X-PF-Store-Id"] = store
    return h


def get(path, **params):
    r = http("GET", BASE + path, headers=_headers(), params=params)
    raise_for(r, f"Printful GET {path}")
    return r.json()["result"]


def post(path, body, **params):
    r = http("POST", BASE + path, headers=_headers(), json=body, params=params)
    raise_for(r, f"Printful POST {path}")
    return r.json()["result"]


def _size_match(want, have):
    if want.lower() == have.lower():
        return True
    if re.search(r"\d", want):
        digits = lambda s: re.sub(r"[^0-9.]", "", s)
        return digits(want) == digits(have)
    return False


def resolve_product(key, state):
    """Find the catalog product and its variants for one of our product types."""
    cache = state["cache"].setdefault("printful_products", {})
    if key in cache:
        return cache[key]
    cfg = settings.PRODUCTS[key]
    pid = None
    catalog = get("/products") if cfg["search"] else []
    for term in cfg["search"]:
        for p in catalog:
            hay = f"{p.get('title', '')} {p.get('model', '')} {p.get('brand', '')}".lower()
            if all(w in hay for w in term.lower().split()) and "sheet" not in hay:
                pid = p["id"]
                break
        if pid:
            break
    pid = pid or cfg["fallback"]
    info = get(f"/products/{pid}")
    variants = info["variants"]
    log(f"  Printful product for {key}: #{pid} {info['product'].get('title')}")
    pf = get(f"/mockup-generator/printfiles/{pid}")
    printfiles = {p["printfile_id"]: p for p in pf["printfiles"]}
    vmap = {v["variant_id"]: v["placements"] for v in pf["variant_printfiles"]}

    chosen = {}
    color_groups = cfg["colors"] or {"white": [None]}
    for group, colors in color_groups.items():
        for color in colors:
            for size in cfg["sizes"]:
                v = next((v for v in variants
                          if (color is None or v.get("color", "").lower() == color.lower())
                          and _size_match(size, v.get("size", "")) and v.get("in_stock", True)), None)
                if not v:
                    have = sorted({x.get("size", "") for x in variants})
                    log(f"    no Printful variant for {key} {color or ''} {size} (Printful has: {have})")
                    continue
                pf_id = vmap.get(v["id"], {}).get(cfg["placement"])
                if not pf_id:
                    continue
                p = printfiles[pf_id]
                chosen[str(v["id"])] = {
                    "group": group, "color": color, "size": size, "cost": float(v["price"]),
                    "printfile_id": pf_id, "w": p["width"], "h": p["height"],
                }
    result = {"product_id": pid, "title": info["product"].get("title"), "variants": chosen}
    cache[key] = result
    return result


def mockups(product_id, variant_ids, placement, image_url, w, h):
    """Ask Printful's mockup generator for product photos. Returns image URLs."""
    body = {
        "variant_ids": variant_ids,
        "format": "jpg",
        "files": [{"placement": placement, "image_url": image_url,
                   "position": {"area_width": w, "area_height": h, "width": w, "height": h,
                                "top": 0, "left": 0}}],
    }
    task = post(f"/mockup-generator/create-task/{product_id}", body)
    key = task["task_key"]
    for _ in range(40):
        time.sleep(6)
        res = get("/mockup-generator/task", task_key=key)
        if res["status"] == "completed":
            urls = []
            for m in res.get("mockups", []):
                urls.append(m["mockup_url"])
                urls += [x["url"] for x in m.get("extra", [])]
            return urls
        if res["status"] == "failed":
            raise RuntimeError(f"Mockup failed: {res.get('error')}")
    raise RuntimeError("Mockup timed out")


def create_order(external_id, recipient, items, confirm):
    return post("/orders", {"external_id": external_id, "recipient": recipient, "items": items},
                confirm="true" if confirm else "false")


def get_order(external_id):
    r = http("GET", f"{BASE}/orders/@{external_id}", headers=_headers())
    if r.status_code == 404:
        return None
    raise_for(r, "Printful order lookup")
    return r.json()["result"]
