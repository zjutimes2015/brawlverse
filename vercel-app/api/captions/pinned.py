import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _db import q_one, send, send_cors_preflight

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_GET(self):
        row = q_one(
            """SELECT id, text, nickname, created_at FROM fan_captions
               WHERE status = 'approved' AND pinned = 1
               ORDER BY created_at DESC LIMIT 1"""
        )
        send(self, 200, {"pinned": dict(row) if row else None})
