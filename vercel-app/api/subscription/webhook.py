import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from _entitlements import PAID_TIERS  # noqa: E402
from _db import q_one, q_write, send, send_cors_preflight  # noqa: E402

from http.server import BaseHTTPRequestHandler


def _upsert_sub(device_hash, tier, status, customer_id="", sub_id="", period_end=0):
    now = time.time()
    q_write(
        """INSERT INTO subscriptions
             (device_hash, tier, status, stripe_customer_id, stripe_subscription_id,
              current_period_end, created_at, updated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (device_hash) DO UPDATE SET
             tier = EXCLUDED.tier, status = EXCLUDED.status,
             stripe_customer_id = EXCLUDED.stripe_customer_id,
             stripe_subscription_id = EXCLUDED.stripe_subscription_id,
             current_period_end = EXCLUDED.current_period_end,
             updated_at = EXCLUDED.updated_at""",
        (device_hash, tier, status, customer_id, sub_id, period_end, now, now),
    )


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_POST(self):
        secret = os.environ.get("STRIPE_SECRET_KEY", "")
        wh_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        if not secret or not wh_secret:
            send(self, 501, {"error": "stripe not configured"})
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        payload = self.rfile.read(length) if length else b""
        sig = self.headers.get("Stripe-Signature", "")
        try:
            import stripe
            event = stripe.Webhook.construct_event(payload, sig, wh_secret)
        except Exception as e:
            send(self, 400, {"error": "bad signature: " + str(e)[:120]})
            return
        etype = event.get("type", "")
        obj = event.get("data", {}).get("object", {}) or {}
        try:
            if etype == "checkout.session.completed":
                md = obj.get("metadata", {}) or {}
                dh, tier = md.get("device_hash", ""), md.get("tier", "")
                if dh and tier in PAID_TIERS:
                    sub_id = (obj.get("subscription") or "")
                    customer = obj.get("customer") or ""
                    period_end = 0
                    if sub_id:
                        stripe.api_key = secret
                        sub = stripe.Subscription.retrieve(sub_id)
                        period_end = sub.get("current_period_end", 0)
                    _upsert_sub(dh, tier, "active", customer, sub_id, period_end)
            elif etype == "customer.subscription.updated":
                md = obj.get("metadata", {}) or {}
                dh = md.get("device_hash", "") or self._dh_by_sub(obj.get("id", ""))
                if dh:
                    _upsert_sub(dh, md.get("tier", "ringside"), obj.get("status", "active"),
                                obj.get("customer", ""), obj.get("id", ""),
                                obj.get("current_period_end", 0))
            elif etype == "customer.subscription.deleted":
                dh = self._dh_by_sub(obj.get("id", ""))
                if dh:
                    _upsert_sub(dh, "free", "canceled")
        except Exception as e:
            send(self, 500, {"error": "handler failed: " + str(e)[:160]})
            return
        send(self, 200, {"ok": True, "type": etype})

    def _dh_by_sub(self, sub_id):
        if not sub_id:
            return ""
        r = q_one("SELECT device_hash FROM subscriptions WHERE stripe_subscription_id = %s", (sub_id,))
        return r["device_hash"] if r else ""
