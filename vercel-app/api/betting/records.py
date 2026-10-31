import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from _db import q_all, send, send_cors_preflight  # noqa: E402

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_GET(self):
        rows = q_all("SELECT fighter, wins, losses, kos FROM fighter_records ORDER BY wins DESC, kos DESC")
        send(self, 200, {"records": [
            {"fighter": r["fighter"], "wins": r["wins"], "losses": r["losses"], "kos": r["kos"]}
            for r in rows]})
