import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _db import (CHOICES, check_rate, client_ip, q_one, q_write, read_json,
                 send, send_cors_preflight, sha)

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_POST(self):
        try:
            v = read_json(self)
        except Exception:
            send(self, 400, {"error": "bad json"})
            return
        choice = str(v.get("choice", "")).strip().lower()
        if choice not in CHOICES:
            send(self, 400, {"error": "choice must be heavy|dodge|guard"})
            return
        bout_id, round_no, device_id = v.get("bout_id"), v.get("round_no"), v.get("device_id")
        if not bout_id or not round_no or not device_id or len(str(device_id)) < 8:
            send(self, 400, {"error": "bout_id, round_no, device_id required"})
            return
        ip = client_ip(self)
        if not check_rate(ip):
            send(self, 429, {"error": "rate limited: slow down"})
            return
        bout = q_one("SELECT * FROM bouts WHERE id = %s", (bout_id,))
        if not bout:
            send(self, 404, {"error": "bout not found"})
            return
        if not bout["voting_open"]:
            send(self, 409, {"error": "voting is closed for this bout"})
            return
        ua = self.headers.get("User-Agent", "")
        now = time.time()
        q_write(
            """INSERT INTO votes (bout_id, round_no, choice, device_hash, ip, ip_ua, created_at, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (bout_id, round_no, device_hash)
               DO UPDATE SET choice = EXCLUDED.choice, updated_at = EXCLUDED.updated_at""",
            (bout_id, int(round_no), choice, sha(str(device_id)), ip, sha(ip + "|" + ua), now, now),
        )
        send(self, 200, {"ok": True, "bout_id": bout_id, "round_no": int(round_no), "choice": choice})
