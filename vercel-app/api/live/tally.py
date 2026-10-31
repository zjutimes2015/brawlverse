"""回合结算（admin）：截止投票 → 加权计票 → 锁定胜者分支 → REVEAL。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from _db import q_all, q_one, q_write, read_json, require_admin, send, send_cors_preflight  # noqa: E402

from http.server import BaseHTTPRequestHandler


def settle_round(rid):
    r = q_one("SELECT * FROM live_rounds WHERE id=%s", (rid,)) if rid else None
    if not r:
        return 404, {"error": "round not found"}
    if r["state"] not in ("VOTING", "LOCKED"):
        return 409, {"error": "round is not awaiting tally (state=%s)" % r["state"]}
    rows = q_all("SELECT choice, SUM(weight) AS w FROM votes WHERE bout_id=%s AND round_no=%s"
                 " AND choice IN (%s,%s) GROUP BY choice",
                 (r["bout_id"], r["round_no"], r["tactic_a"], r["tactic_b"]))
    tally = {row["choice"]: int(row["w"] or 0) for row in rows}
    wa = tally.get(r["tactic_a"], 0)
    wb = tally.get(r["tactic_b"], 0)
    # 平票 → tactic_a（确定性；admin 可在 REVEAL 前手动覆盖）
    winner = "a" if wa >= wb else "b"
    now = time.time()
    q_write("UPDATE live_rounds SET winning_branch=%s, state='REVEAL' WHERE id=%s",
            (winner, rid))
    url = r["branch_a_url"] if winner == "a" else r["branch_b_url"]
    return 200, {"ok": True, "round_id": rid, "tally": tally,
                 "winning_branch": winner,
                 "winning_tactic": r["tactic_a"] if winner == "a" else r["tactic_b"],
                 "video_url": url, "settled_at": now}


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_POST(self):
        if not require_admin(self):
            send(self, 403, {"error": "admin only"})
            return
        try:
            v = read_json(self)
        except Exception:
            send(self, 400, {"error": "bad json"})
            return
        status, d = settle_round(v.get("round_id"))
        send(self, status, d)
