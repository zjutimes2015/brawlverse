import os
import sys
import time
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _db import q_all, send, send_cors_preflight

from http.server import BaseHTTPRequestHandler

FEED_WINDOW_S = 30 * 60
FEED_LIMIT = 50


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        since_id = int(qs.get("since_id", ["0"])[0] or 0)
        rows = q_all(
            """SELECT id, text, nickname, created_at FROM fan_captions
               WHERE status = 'approved' AND created_at > %s AND id > %s
               ORDER BY id ASC LIMIT %s""",
            (time.time() - FEED_WINDOW_S, since_id, FEED_LIMIT),
        )
        send(self, 200, {"captions": [dict(r) for r in rows]})
