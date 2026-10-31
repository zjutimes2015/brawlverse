import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _db import q_all, send, send_cors_preflight

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_GET(self):
        rows = q_all("SELECT * FROM bouts ORDER BY created_at")
        send(self, 200, [
            {"id": r["id"], "title": r["title"], "fighter_a": r["fighter_a"],
             "fighter_b": r["fighter_b"], "round_no": r["round_no"],
             "voting_open": bool(r["voting_open"]),
             "tactic_note": r.get("tactic_note") or ""}
            for r in rows
        ])
