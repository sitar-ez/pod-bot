"""Etsy Open API v3: listings, photos, variations, orders, tracking."""
from pathlib import Path

from .common import ROOT, env, http, log, raise_for

API = "https://openapi.etsy.com/v3/application"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"


class Etsy:
    def __init__(self):
        self.key = env("ETSY_KEYSTRING")
        self.secret = env("ETSY_SHARED_SECRET")
        self._refresh(env("ETSY_REFRESH_TOKEN"))
        self._shop_id = None

    def _refresh(self, refresh_token):
        r = http("POST", TOKEN_URL, data={"grant_type": "refresh_token", "client_id": self.key,
                                          "refresh_token": refresh_token})
        raise_for(r, "Etsy sign-in (refresh token)")
        data = r.json()
        self.token = data["access_token"]
        new_rt = data.get("refresh_token")
        if new_rt and new_rt != refresh_token:
            # The workflow saves this back into GitHub Secrets after the run
            (ROOT / ".new_refresh_token").write_text(new_rt)

    def _h(self):
        return {"x-api-key": f"{self.key}:{self.secret}", "Authorization": f"Bearer {self.token}"}

    def req(self, method, path, what, **kw):
        r = http(method, API + path, headers=self._h(), **kw)
        raise_for(r, f"Etsy {what}")
        return r.json() if r.text else {}

    # ---- shop setup lookups ------------------------------------------------
    @property
    def shop_id(self):
        if not self._shop_id:
            me = self.req("GET", "/users/me", "who am I")
            self._shop_id = me["shop_id"]
        return self._shop_id

    def shipping_profiles(self):
        return self.req("GET", f"/shops/{self.shop_id}/shipping-profiles", "shipping profiles")["results"]

    def readiness_states(self):
        return self.req("GET", f"/shops/{self.shop_id}/readiness-state-definitions",
                        "processing profiles")["results"]

    def production_partners(self):
        return self.req("GET", f"/shops/{self.shop_id}/production-partners", "production partners")["results"]

    def taxonomy(self):
        return self.req("GET", "/seller-taxonomy/nodes", "categories")["results"]

    # ---- listings ------------------------------------------------------------
    def create_draft(self, body):
        return self.req("POST", f"/shops/{self.shop_id}/listings", "create listing", json=body)

    def upload_image(self, listing_id, jpg_bytes, rank):
        return self.req("POST", f"/shops/{self.shop_id}/listings/{listing_id}/images", "upload photo",
                        files={"image": (f"photo{rank}.jpg", jpg_bytes, "image/jpeg")},
                        data={"rank": rank})

    def set_inventory(self, listing_id, body):
        return self.req("PUT", f"/listings/{listing_id}/inventory", "set variations", json=body)

    def activate(self, listing_id):
        return self.req("PATCH", f"/shops/{self.shop_id}/listings/{listing_id}", "publish listing",
                        json={"state": "active"})

    # ---- orders --------------------------------------------------------------
    def unshipped_receipts(self):
        return self.req("GET", f"/shops/{self.shop_id}/receipts", "orders",
                        params={"was_paid": "true", "was_shipped": "false", "limit": 100})["results"]

    def add_tracking(self, receipt_id, code, carrier):
        body = {"tracking_code": code, "carrier_name": carrier}
        try:
            return self.req("POST", f"/shops/{self.shop_id}/receipts/{receipt_id}/tracking",
                            "add tracking", data=body)
        except RuntimeError as e:
            log("  carrier name refused, retrying as 'other':", e)
            body["carrier_name"] = "other"
            return self.req("POST", f"/shops/{self.shop_id}/receipts/{receipt_id}/tracking",
                            "add tracking", data=body)


AVOID = ("baby", "kid", "girl", "boy", "women", "men's", "dog", "pet", "doll", "toddler", "pattern",
         "supplies", "digital")
PREFER = ("gender-neutral adult", "unisex adult", "home & living", "paper & party")


def find_category(nodes, words):
    """Search Etsy's category tree for the best node for this product. Returns (id, path)."""
    best, best_score = None, -99
    stack = [(n, n.get("name", "")) for n in nodes]
    while stack:
        n, path = stack.pop(0)
        name, low = n.get("name", "").lower(), path.lower()
        if any(w == name for w in words) or any(w in name for w in words):
            score = (3 if any(w == name for w in words) else 1)
            score += 3 if any(p in low for p in PREFER) else 0
            score -= 5 if any(a in low for a in AVOID) else 0
            if score > best_score:
                best, best_score = (n["id"], path), score
        stack.extend((c, f"{path} > {c.get('name', '')}") for c in n.get("children", []))
    return best or (None, None)
