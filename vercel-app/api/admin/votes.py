import os
import sys
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _db import q_all, require_admin, send, send_cors_preflight

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_GET(self):
        if not require_admin(self):
            send(self, 403, {"error": "bad admin token"}, cors=False)
            return
        qs = parse_qs(urlparse(self.path).query)
        bout_id = qs.get("bout_id", [None])[0]
        if bout_id:
            rows = q_all("SELECT * FROM votes WHERE bout_id = %s ORDER BY updated_at DESC LIMIT 500",
                         (bout_id,))
        else:
            rows = q_all("SELECT * FROM votes ORDER BY updated_at DESC LIMIT 500")
        send(self, 200, [dict(r) for r in rows], cors=False)
