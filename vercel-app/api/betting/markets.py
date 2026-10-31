import json as _json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from _common import pool_totals  # noqa: E402
from _db import q_all, send, send_cors_preflight  # noqa: E402

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_GET(self):
        markets = q_all(
            "SELECT * FROM bet_markets WHERE status IN ('open','locked') ORDER BY created_at DESC"
        )
        out = []
        for m in markets:
            sels = _json.loads(m["selections"])
            pools = pool_totals(m["id"])
            total = sum(pools.values())
            odds = {s: (round(total / pools[s], 2) if pools.get(s) else None) for s in sels}
            try:
                house = _json.loads(m.get("house_pool") or "{}")
            except Exception:
                house = {}
            out.append({
                "id": m["id"], "bout_id": m["bout_id"], "market_type": m["market_type"],
                "question": m["question"], "selections": sels, "status": m["status"],
                "pools": pools, "total_pool": total, "implied_odds": odds,
                "house_seed": house,
            })
        send(self, 200, {"markets": out})
