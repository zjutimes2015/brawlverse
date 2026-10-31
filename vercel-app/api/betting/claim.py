import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from _common import DAILY_CLAIM, DAY_S, get_wallet  # noqa: E402
from _db import (check_rate, client_ip, q_write, read_json, send,  # noqa: E402
                 send_cors_preflight, sha)

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
        device_id = v.get("device_id")
        if not device_id or len(str(device_id)) < 8:
            send(self, 400, {"error": "device_id required"})
            return
        ip = client_ip(self)
        if not check_rate(ip):
            send(self, 429, {"error": "rate limited: slow down"})
            return
        dh = sha(str(device_id))
        w = get_wallet(dh)
        now = time.time()
        if now - w["last_claim"] < DAY_S:
            send(self, 409, {"error": "already claimed",
                             "next_claim_in_s": int(DAY_S - (now - w["last_claim"])),
                             "balance": w["balance"]})
            return
        q_write("UPDATE bet_wallets SET balance = balance + %s, last_claim = %s WHERE device_hash = %s",
                (DAILY_CLAIM, now, dh))
        q_write(
            "INSERT INTO bet_ledger (device_hash, delta, reason, ref, created_at) VALUES (%s,%s,%s,%s,%s)",
            (dh, DAILY_CLAIM, "daily_claim", "", now),
        )
        send(self, 200, {"ok": True, "claimed": DAILY_CLAIM, "balance": w["balance"] + DAILY_CLAIM})
