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
        rows = q_all(
            "SELECT device_hash, balance FROM bet_wallets ORDER BY balance DESC LIMIT 20"
        )
        board = [{"rank": i + 1, "player": r["device_hash"][:8], "balance": r["balance"]}
                 for i, r in enumerate(rows)]
        send(self, 200, {"leaderboard": board})
