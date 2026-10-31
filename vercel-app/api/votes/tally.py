import os
import sys
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _db import q_all, send, send_cors_preflight

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        bout_id = qs.get("bout_id", [None])[0]
        round_no = int(qs.get("round_no", ["1"])[0] or 1)
        rows = q_all(
            "SELECT choice, COUNT(*) AS n FROM votes WHERE bout_id = %s AND round_no = %s GROUP BY choice",
            (bout_id, round_no),
        )
        tally = {"heavy": 0, "dodge": 0, "guard": 0}
        for r in rows:
            tally[r["choice"]] = r["n"]
        send(self, 200, {"bout_id": bout_id, "round_no": round_no, "tally": tally,
                         "total": sum(tally.values())})
