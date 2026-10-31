import json as _json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))
from _common import pool_totals, settle_market  # noqa: E402
from _db import (q_all, q_one, q_write, read_json, require_admin, send,  # noqa: E402
                 send_cors_preflight)

from http.server import BaseHTTPRequestHandler

MARKET_TYPES = {"winner", "method", "round"}


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def _auth(self):
        if not require_admin(self):
            send(self, 403, {"error": "forbidden"})
            return False
        return True

    def do_GET(self):
        if not self._auth():
            return
        ms = q_all("SELECT * FROM bet_markets ORDER BY created_at DESC")
        out = []
        for m in ms:
            pools = pool_totals(m["id"])
            out.append({"id": m["id"], "bout_id": m["bout_id"], "market_type": m["market_type"],
                        "question": m["question"], "selections": _json.loads(m["selections"]),
                        "status": m["status"], "pools": pools, "total_pool": sum(pools.values()),
                        "winning_selection": m["winning_selection"]})
        send(self, 200, {"markets": out})

    def do_POST(self):
        if not self._auth():
            return
        try:
            v = read_json(self)
        except Exception:
            send(self, 400, {"error": "bad json"})
            return
        mid = str(v.get("id", "")).strip()
        bout_id = str(v.get("bout_id", "")).strip()
        mtype = str(v.get("market_type", "")).strip()
        question = str(v.get("question", "")).strip()
        sels = v.get("selections")
        if not mid or not bout_id or mtype not in MARKET_TYPES or not question:
            send(self, 400, {"error": "id, bout_id, market_type(winner|method|round), question required"})
            return
        if not isinstance(sels, list) or len(sels) < 2:
            send(self, 400, {"error": "selections must be a list of 2+"})
            return
        if q_one("SELECT id FROM bet_markets WHERE id = %s", (mid,)):
            send(self, 409, {"error": "market id exists"})
            return
        house = v.get("house_pool") or {}
        if not isinstance(house, dict):
            send(self, 400, {"error": "house_pool must be an object {selection: amount}"})
            return
        for s, amt in house.items():
            if s not in sels:
                send(self, 400, {"error": "house_pool selection not in selections: " + s})
                return
            try:
                house[s] = int(amt)
            except Exception:
                send(self, 400, {"error": "house_pool amounts must be integers"})
                return
        now = time.time()
        q_write(
            "INSERT INTO bet_markets (id, bout_id, market_type, question, selections, house_pool, status, created_at)"
            " VALUES (%s,%s,%s,%s,%s,%s,'open',%s)",
            (mid, bout_id, mtype, question, _json.dumps(sels), _json.dumps(house), now),
        )
        send(self, 200, {"ok": True, "id": mid})

    def do_PATCH(self):
        if not self._auth():
            return
        qs = self.path.split("?", 1)
        params = dict(p.split("=", 1) for p in qs[1].split("&") if "=" in p) if len(qs) > 1 else {}
        mid = params.get("id", "")
        try:
            v = read_json(self)
        except Exception:
            v = {}
        action = str(v.get("action", "")).strip()
        m = q_one("SELECT * FROM bet_markets WHERE id = %s", (mid,))
        if not m:
            send(self, 404, {"error": "market not found"})
            return
        if action == "lock":
            if m["status"] != "open":
                send(self, 409, {"error": "market is %s" % m["status"]})
                return
            q_write("UPDATE bet_markets SET status='locked' WHERE id=%s", (mid,))
            send(self, 200, {"ok": True, "id": mid, "status": "locked"})
        elif action == "settle":
            if m["status"] == "settled":
                send(self, 409, {"error": "already settled"})
                return
            winner = str(v.get("winning_selection", "")).strip()
            res = settle_market(mid, winner)
            if not res:
                send(self, 400, {"error": "invalid winning_selection"})
                return
            send(self, 200, {"ok": True, "id": mid, **res})
        else:
            send(self, 400, {"error": "action must be lock|settle"})
