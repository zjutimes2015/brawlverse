import os
import sys
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _db import q_all, q_write, read_json, require_admin, send, send_cors_preflight  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "subscription"))
from _entitlements import TIERS  # noqa: E402

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def _auth(self):
        if not require_admin(self):
            send(self, 403, {"error": "forbidden"}, cors=False)
            return False
        return True

    def do_GET(self):
        if not self._auth():
            return
        rows = q_all(
            "SELECT device_hash, tier, status, current_period_end FROM subscriptions"
            " ORDER BY updated_at DESC LIMIT 100"
        )
        import time
        out = [{"player": r["device_hash"][:8], "tier": r["tier"], "status": r["status"],
                "period_end": time.strftime("%Y-%m-%d", time.gmtime(r["current_period_end"]))
                if r["current_period_end"] else "-"} for r in rows]
        send(self, 200, {"subscriptions": out, "tiers": list(TIERS)}, cors=False)

    def do_PATCH(self):
        # manual grant / revoke (comps, testing): /api/admin/subscriptions?device_hash=<sha>
        if not self._auth():
            return
        qs = parse_qs(urlparse(self.path).query)
        dh = qs.get("device_hash", [None])[0]
        if not dh:
            send(self, 400, {"error": "missing ?device_hash="}, cors=False)
            return
        try:
            p = read_json(self)
        except Exception:
            p = {}
        tier = str(p.get("tier", "free")).strip()
        if tier not in TIERS:
            send(self, 400, {"error": "tier must be free|ringside|booker|promoter"}, cors=False)
            return
        import time
        now = time.time()
        q_write(
            """INSERT INTO subscriptions (device_hash, tier, status, created_at, updated_at)
               VALUES (%s,%s,'active',%s,%s)
               ON CONFLICT (device_hash) DO UPDATE SET tier = EXCLUDED.tier,
                 status = 'active', updated_at = EXCLUDED.updated_at""",
            (dh, tier, now, now),
        )
        send(self, 200, {"ok": True, "device_hash": dh[:8], "tier": tier}, cors=False)
