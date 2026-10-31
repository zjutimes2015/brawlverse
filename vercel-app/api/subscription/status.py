import os
import sys
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from _entitlements import TIERS, entitlements  # noqa: E402
from _db import send, send_cors_preflight, sha  # noqa: E402

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        device_id = qs.get("device_id", [None])[0]
        if not device_id or len(device_id) < 8:
            send(self, 400, {"error": "device_id required"})
            return
        e = entitlements(sha(device_id))
        send(self, 200, {"entitlements": e,
                         "tiers": {k: {"price_monthly": v["price_monthly"]} for k, v in TIERS.items()}})
