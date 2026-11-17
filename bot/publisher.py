"""Publisher: approved design -> Printful mockups -> live Etsy listings."""
import math
import os
import re

from . import audit, personalize, printful, render, settings, telegram
from .common import http, log, now_iso, public_url
from .etsy import find_category

TAG_OK = re.compile(r"[^A-Za-z0-9 \-']")


def price_for(cost, cfg):
    p = max(cfg["min_price"], cost * cfg["markup"])
    return math.ceil(p) - 0.01


def clean_tags(tags):
    out = []
    for t in tags:
        t = TAG_OK.sub("", t).strip()[:20].strip()
        if t and t.lower() not in [o.lower() for o in out]:
            out.append(t)
    return out[:13]


APPAREL = {"tee", "tee_bc", "hoodie", "crewneck"}


def listing_description(design, key):
    cfg = settings.PRODUCTS[key]
    return (design["description"].strip() + "\n\n" + cfg["details"] +
            (" See the size chart in the photos." if key in APPAREL else "") +
            (personalize.DESCRIPTION if design.get("personalize") else "") +
            settings.RETURNS + settings.DISCLOSURE.format(shop=settings.SHOP_NAME))


def update_live_policies(design, etsy, state):
    """Bring an already-live design's listings up to date: return policy and description."""
    shop = shop_setup(etsy, state)
    for key, lid in design.get("listings", {}).items():
        body = {"description": listing_description(design, key)}
        if shop.get("return_policy_id"):
            body["return_policy_id"] = shop["return_policy_id"]
        etsy.update_listing(lid, body)
        log(f"  updated policy and description for {design['id']} {key}")


def build_photos(design, key, info, cfg, variants):
    """Listing photos: Printful mockups in several styles for the first color, a plain shot of
    each other color, then a size chart for apparel. Returns a list of JPEG bytes (max 10)."""
    by_color = {}
    for vid, v in variants.items():
        by_color.setdefault(v["color"], vid)
    styles = printful.mockup_styles(info["product_id"])
    urls = []
    for i, (color, vid) in enumerate(by_color.items()):
        v = variants[vid]
        try:
            urls += printful.mockups(info["product_id"], [int(vid)], info.get("placement", cfg["placement"]),
                                     public_url(design["files"][key][vid]), v["w"], v["h"],
                                     styles=styles if i == 0 else None)
        except Exception as e:
            if i == 0 and styles:      # if a style is refused, fall back to the default mockup
                log("  styled mockups failed, using default:", e)
                urls += printful.mockups(info["product_id"], [int(vid)], info.get("placement", cfg["placement"]),
                                         public_url(design["files"][key][vid]), v["w"], v["h"])
            else:
                raise
    seen, photos = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            photos.append(u)
    limit = 8 if key in APPAREL else 9   # Etsy allows 10 photos; leave room while swapping
    images = [http("GET", u).content for u in photos[:limit]]
    if key in APPAREL:
        chart = printful.size_chart(info["product_id"])
        if chart:   # only the sizes this shop sells
            keep = [i for i, z in enumerate(chart["sizes"]) if any(z.lower() == s.lower() for s in cfg["sizes"])]
            if keep:
                chart["sizes"] = [chart["sizes"][i] for i in keep]
                chart["rows"] = [(lab, [vals[i] for i in keep if i < len(vals)]) for lab, vals in chart["rows"]]
            images.append(render.size_chart_image(cfg["label"], chart))
    log(f"  {key}: {len(images)} photos ({len(styles)} mockup styles{', size chart' if key in APPAREL else ''})")
    return images


def shop_setup(etsy, state):
    """Find shipping profile, processing profile, production partner and categories once."""
    c = state["cache"].setdefault("etsy", {})
    if c.get("ready") and "return_policy_id" in c:
        return c
    sp = os.getenv("ETSY_SHIPPING_PROFILE_ID")
    if not sp:
        profiles = etsy.shipping_profiles()
        if not profiles:
            raise RuntimeError("Your Etsy shop has no shipping profile yet. Create one in Shop Manager > Settings > Delivery.")
        sp = profiles[0]["shipping_profile_id"]
    c["shipping_profile_id"] = int(sp)

    rs = os.getenv("ETSY_READINESS_STATE_ID")
    if not rs:
        states = etsy.readiness_states()
        made = [s for s in states if s.get("readiness_state") == "made_to_order"] or states
        if not made:
            raise RuntimeError("No processing profile found. Create one in Etsy (made to order, 2-7 days).")
        rs = made[0]["readiness_state_id"]
    c["readiness_state_id"] = int(rs)

    partners = etsy.production_partners()
    log(f"  Etsy production partners: {partners}")
    pf = [p["production_partner_id"] for p in partners
          if "printful" in " ".join(str(v) for v in p.values()).lower()]
    if not pf and len(partners) == 1:
        pf = [partners[0]["production_partner_id"]]   # only one partner: that's Printful
    if not pf:
        raise RuntimeError("Etsy shows no production partner yet. Add Printful in Shop Manager > Settings > "
                           "Production partners, and make sure it was saved.")
    c["production_partner_ids"] = pf[:1]

    # Return policy: no returns or exchanges (misprints and damage are handled in the description,
    # and Printful covers them). Etsy ranks listings without a policy lower.
    try:
        pols = etsy.return_policies()
        pol = next((p for p in pols if not p.get("accepts_returns") and not p.get("accepts_exchanges")), None)
        if not pol:
            pol = etsy.create_return_policy({"accepts_returns": False, "accepts_exchanges": False})
        c["return_policy_id"] = pol["return_policy_id"]
    except Exception as e:
        log("  couldn't set up the return policy (listings will still post):", e)

    nodes = etsy.taxonomy()
    c["taxonomy"] = {}
    for key, cfg in settings.PRODUCTS.items():
        override = os.getenv(f"ETSY_CATEGORY_{key.upper()}")
        tid, path = (int(override), "override") if override else find_category(nodes, cfg["etsy_category"])
        c["taxonomy"][key] = tid
        log(f"  Etsy category for {key}: {tid} ({path})")
    c["ready"] = True
    return c


def publish(design, etsy, state):
    shop = shop_setup(etsy, state)
    did = design["id"]
    if not design.get("tags") or not design.get("description"):
        from . import copywriter, telegram
        if not copywriter.write(design, state):
            design["status"] = "pending"
            telegram.send(f"⚠️ I couldn't write safe Etsy titles and tags for {did}, so it's back in your "
                          "queue. Tap ✏️ Edit on it with a note, or Skip it.")
            return
    for key in design["products"]:
        if key in design["listings"]:
            continue
        cfg = settings.PRODUCTS[key]
        info = printful.resolve_product(key, state)
        variants = {vid: v for vid, v in info["variants"].items() if vid in design["files"][key]}
        if not variants:
            log(f"  {did}: no variants for {key}, skipping")
            continue

        photos = build_photos(design, key, info, cfg, variants)

        # Prices: same price for a size across colors
        size_price = {}
        for v in variants.values():
            size_price[v["size"]] = max(size_price.get(v["size"], 0), price_for(v["cost"], cfg))
        base_price = min(size_price.values())

        title = (design["titles"].get(key) or (design["titles"].get("tee") if key == "tee_bc" else None)
                 or f"{' '.join(design['lines'])} {cfg['label']}")[:140]
        desc = listing_description(design, key)
        body = {
            "quantity": 999, "title": title, "description": desc, "price": base_price,
            "who_made": "i_did", "when_made": "made_to_order", "is_supply": False,
            "taxonomy_id": shop["taxonomy"][key], "type": "physical",
            "shipping_profile_id": shop["shipping_profile_id"],
            "readiness_state_id": shop["readiness_state_id"],
            "production_partner_ids": shop["production_partner_ids"],
            "tags": clean_tags(design["tags"]),
        }
        if shop.get("return_policy_id"):
            body["return_policy_id"] = shop["return_policy_id"]

        products = []
        for vid, v in variants.items():
            props = []
            if cfg["colors"]:
                props.append({"property_id": 513, "property_name": "Color", "value_ids": [], "values": [v["color"]]})
            props.append({"property_id": 514 if cfg["colors"] else 513, "property_name": "Size",
                          "value_ids": [], "values": [v["size"]]})
            products.append({
                "sku": f"PB-{did}-{vid}", "property_values": props,
                "offerings": [{"price": size_price[v["size"]], "quantity": 999, "is_enabled": True,
                               "readiness_state_id": shop["readiness_state_id"]}],
            })
        size_prop = 514 if cfg["colors"] else 513
        inventory = {
            "products": products,
            # Etsy requires price to follow either none or all of the variation properties
            "price_on_property": ([513, 514] if cfg["colors"] else [513]) if len(set(size_price.values())) > 1 else [],
            "quantity_on_property": [],
            "sku_on_property": [513, 514] if cfg["colors"] else [513],
            "readiness_state_on_property": [],
        }

        if settings.DRY_RUN:
            log(f"  [dry run] would list {did} {key}: '{title}' at ${base_price}, "
                f"{len(products)} variants, {len(photos)} photos")
            continue

        partial = design.setdefault("partial", {})
        lid = partial.get(key)
        if not lid:   # if a previous run died halfway, finish that draft instead of making another
            lid = etsy.create_draft(body)["listing_id"]
            partial[key] = lid
            for rank, img in enumerate(photos, start=1):
                etsy.upload_image(lid, img, rank)
        etsy.set_inventory(lid, inventory)
        if design.get("personalize"):
            try:
                etsy.set_personalization(lid, personalize.QUESTION)
            except Exception as e:
                log("  name box failed:", e)
                telegram.send(f"⚠️ Couldn't add the name box to {did} {key} (it's listed with "
                              f"\"{design['personalize']['sample']}\" as shown): {str(e)[:200]}")
        if settings.PUBLISH_LIVE:
            etsy.activate(lid)
        design["listings"][key] = lid
        log(f"  listed {did} {key}: https://www.etsy.com/listing/{lid}")

    if settings.DRY_RUN:
        design["status"] = "approved_dry"   # gets listed for real once dry run is switched off
        telegram.send(f"🧪 {did} passed a dry run: mockups worked and the listings are ready. "
                      "It will go live automatically when you switch dry run off.")
        return
    design["status"] = "published"
    design["published"] = now_iso()
    audit.record(state, did, "published", via="automatic", listings=dict(design["listings"]),
                 photos=audit.PHOTO_BASIS)
    links = "\n".join(f"{k}: https://www.etsy.com/listing/{v}" for k, v in design["listings"].items())
    telegram.send(f"✅ {did} is live on Etsy.\n{links}")


def refresh_photos(design, keys, etsy, state):
    """After a design's print files change, make new Printful mockups and swap the photos
    on its live Etsy listings. Orders already use the new files (they're read at order time)."""
    did = design["id"]
    done = []
    for key in keys:
        lid = design["listings"].get(key)
        if not lid:
            continue
        cfg = settings.PRODUCTS[key]
        info = printful.resolve_product(key, state)
        variants = {vid: info["variants"][vid] for vid in design["files"][key] if vid in info["variants"]}
        photos = build_photos(design, key, info, cfg, variants)
        if not photos:
            continue
        old = etsy.listing_images(lid)
        for img in old[1:]:                              # keep one old photo so the listing is never empty
            etsy.delete_image(lid, img["listing_image_id"])
        for rank, img in enumerate(photos, start=1):
            etsy.upload_image(lid, img, rank)
        for img in old[:1]:
            etsy.delete_image(lid, img["listing_image_id"])
        done.append(f"{key}: https://www.etsy.com/listing/{lid}")
        log(f"  refreshed photos for {did} {key}")
    if done:
        telegram.send(f"📸 Updated photos for {did} (Printful mockups plus a size chart on apparel):\n" + "\n".join(done))
