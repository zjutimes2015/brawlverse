import json as _json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "subscription"))
from _common import MAX_BET, get_wallet  # noqa: E402
from _entitlements import entitlements  # noqa: E402
from _db import (check_rate, client_ip, q_one, q_write, read_json, send,  # noqa: E402
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
        market_id = str(v.get("market_id", "")).strip()
        selection = str(v.get("selection", "")).strip()
        device_id = v.get("device_id")
        try:
            amount = int(v.get("amount", 0))
        except Exception:
            amount = 0
        if not market_id or not selection or not device_id or len(str(device_id)) < 8:
            send(self, 400, {"error": "market_id, selection, device_id required"})
            return
        dh = sha(str(device_id))
        cap = MAX_BET * entitlements(dh)["bet_max_mult"]
        if amount <= 0 or amount > cap:
            send(self, 400, {"error": "amount must be 1..%d" % cap})
            return
        ip = client_ip(self)
        if not check_rate(ip):
            send(self, 429, {"error": "rate limited: slow down"})
            return
        m = q_one("SELECT * FROM bet_markets WHERE id = %s", (market_id,))
        if not m:
            send(self, 404, {"error": "market not found"})
            return
        if m["status"] != "open":
            send(self, 409, {"error": "market is %s" % m["status"]})
            return
        if selection not in _json.loads(m["selections"]):
            send(self, 400, {"error": "invalid selection"})
            return
        dh = sha(str(device_id))
        w = get_wallet(dh)
        if w["balance"] < amount:
            send(self, 409, {"error": "insufficient balance", "balance": w["balance"]})
            return
        ua = self.headers.get("User-Agent", "")
        now = time.time()
        q_write("UPDATE bet_wallets SET balance = balance - %s WHERE device_hash = %s", (amount, dh))
        q_write(
            "INSERT INTO bets (market_id, device_hash, selection, amount, ip_ua, created_at)"
            " VALUES (%s,%s,%s,%s,%s,%s)",
            (market_id, dh, selection, amount, sha(ip + "|" + ua), now),
        )
        q_write(
            "INSERT INTO bet_ledger (device_hash, delta, reason, ref, created_at) VALUES (%s,%s,%s,%s,%s)",
            (dh, -amount, "bet_placed", market_id, now),
        )
        send(self, 200, {"ok": True, "market_id": market_id, "selection": selection,
                         "amount": amount, "balance": w["balance"] - amount})
