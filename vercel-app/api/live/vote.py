"""Friday Fight Night 回合投票。只在 live_round state=VOTING 且未过期时接受。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "subscription"))
from _db import check_rate, client_ip, q_one, q_write, read_json, send, send_cors_preflight, sha  # noqa: E402
from _entitlements import entitlements  # noqa: E402

from http.server import BaseHTTPRequestHandler


def cast_live_vote(rid, choice, device_id, ip, ua):
    if not rid or not device_id or len(str(device_id)) < 8:
        return 400, {"error": "round_id, device_id required"}
    r = q_one("SELECT * FROM live_rounds WHERE id=%s", (rid,))
    if not r:
        return 404, {"error": "round not found"}
    if r["state"] != "VOTING" or time.time() > r["vote_deadline"]:
        return 409, {"error": "voting is not open for this round"}
    if choice not in (r["tactic_a"], r["tactic_b"]):
        return 400, {"error": "choice must be one of the two tactics"}
    if not check_rate(ip):
        return 429, {"error": "rate limited: slow down"}
    dh = sha(str(device_id))
    weight = entitlements(dh)["vote_weight"]
    now = time.time()
    q_write(
        """INSERT INTO votes (bout_id, round_no, choice, device_hash, ip, ip_ua, weight, created_at, updated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (bout_id, round_no, device_hash)
           DO UPDATE SET choice = EXCLUDED.choice, weight = EXCLUDED.weight, updated_at = EXCLUDED.updated_at""",
        (r["bout_id"], r["round_no"], choice, dh, ip, sha(ip + "|" + ua), weight, now, now),
    )
    return 200, {"ok": True, "round_id": rid, "choice": choice, "weight": weight}


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
        status, d = cast_live_vote(v.get("round_id"), choice, v.get("device_id"),
                                   client_ip(self), self.headers.get("User-Agent", ""))
        send(self, status, d)
