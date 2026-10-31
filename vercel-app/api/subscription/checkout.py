import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from _entitlements import PAID_TIERS, stripe_price_id  # noqa: E402
from _db import read_json, send, send_cors_preflight, sha  # noqa: E402

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_POST(self):
        try:
            v = read_json(self)
        except Exception:
            send(self, 400, {"error": "bad json"})
            return
        tier = str(v.get("tier", "")).strip()
        device_id = v.get("device_id")
        if tier not in PAID_TIERS:
            send(self, 400, {"error": "tier must be ringside|booker|promoter"})
            return
        if not device_id or len(str(device_id)) < 8:
            send(self, 400, {"error": "device_id required"})
            return
        secret = os.environ.get("STRIPE_SECRET_KEY", "")
        if not secret:
            send(self, 501, {"error": "stripe not configured (STRIPE_SECRET_KEY missing)"})
            return
        price = stripe_price_id(tier)
        if not price:
            send(self, 501, {"error": "price not configured for tier " + tier})
            return
        try:
            import stripe
            stripe.api_key = secret
            success_url = v.get("success_url") or "https://zjutimes2015.github.io/brawlverse/episodes.html?sub=ok"
            cancel_url = v.get("cancel_url") or "https://zjutimes2015.github.io/brawlverse/episodes.html?sub=cancel"
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": price, "quantity": 1}],
                metadata={"device_hash": sha(str(device_id)), "tier": tier},
                success_url=success_url,
                cancel_url=cancel_url,
            )
        except Exception as e:
            send(self, 502, {"error": "stripe error: " + str(e)[:200]})
            return
        send(self, 200, {"ok": True, "url": session.url, "tier": tier})
