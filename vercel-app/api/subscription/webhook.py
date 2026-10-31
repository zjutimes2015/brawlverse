import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from _entitlements import PAID_TIERS  # noqa: E402
from _waffo import verify_webhook, waffo_configured  # noqa: E402
from _db import q_one, q_write, send, send_cors_preflight  # noqa: E402

from http.server import BaseHTTPRequestHandler


def _upsert_sub(device_hash, tier, status, waffo_sub_id="", period_end=0):
    now = time.time()
    q_write(
        """INSERT INTO subscriptions
             (device_hash, tier, status, waffo_subscription_id,
              current_period_end, created_at, updated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (device_hash) DO UPDATE SET
             tier = EXCLUDED.tier, status = EXCLUDED.status,
             waffo_subscription_id = EXCLUDED.waffo_subscription_id,
             current_period_end = EXCLUDED.current_period_end,
             updated_at = EXCLUDED.updated_at""",
        (device_hash, tier, status, waffo_sub_id, period_end, now, now),
    )


def _period_end(data):
    for k in ("currentPeriodEnd", "current_period_end", "expiresAt", "expires_at"):
        v = data.get(k)
        if v:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
            try:
                from datetime import datetime
                return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
            except Exception:
                pass
    return 0


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_POST(self):
        if not waffo_configured():
            send(self, 501, {"error": "waffo not configured"})
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        payload = self.rfile.read(length) if length else b""
        sig = self.headers.get("x-waffo-signature", "")
        try:
            event = verify_webhook(payload, sig)
        except ValueError as e:
            send(self, 401, {"error": "invalid signature: " + str(e)[:120]})
            return
        # env guard: test events must not touch prod logic
        want_env = os.environ.get("WAFFO_ENV", "")
        if want_env and event.get("mode", "") and event["mode"] != want_env:
            send(self, 200, {"ok": True, "ignored": "env mismatch"})
            return
        # idempotency
        eid = str(event.get("id", ""))
        if eid:
            try:
                q_write("INSERT INTO webhook_events (event_id, created_at) VALUES (%s,%s)",
                        (eid, time.time()))
            except Exception:
                send(self, 200, {"ok": True, "deduped": True})
                return
        etype = event.get("eventType", "")
        data = event.get("data", {}) or {}
        md = data.get("metadata", {}) or {}
        dh = md.get("device_hash", "")
        tier = md.get("tier", "")
        try:
            if etype == "subscription.activated" or (
                    etype == "order.completed" and tier in PAID_TIERS and dh):
                sub_id = str(data.get("subscriptionId") or data.get("id") or "")
                _upsert_sub(dh, tier, "active", sub_id, _period_end(data))
            elif etype == "subscription.past_due":
                if dh:
                    _upsert_sub(dh, tier if tier in PAID_TIERS else "ringside",
                                "past_due", str(data.get("subscriptionId") or ""),
                                _period_end(data))
            elif etype == "subscription.canceled":
                if dh:
                    _upsert_sub(dh, "free", "canceled")
        except Exception as e:
            send(self, 500, {"error": "handler failed: " + str(e)[:160]})
            return
        send(self, 200, {"ok": True, "type": etype})
