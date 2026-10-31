"""Friday Fight Night 直播状态 API。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from _db import q_all, q_one, send, send_cors_preflight  # noqa: E402

from http.server import BaseHTTPRequestHandler


def public_state(r):
    now = time.time()
    d = {"id": r["id"], "bout_id": r["bout_id"], "round_no": r["round_no"],
         "tactic_a": r["tactic_a"], "tactic_b": r["tactic_b"],
         "state": r["state"],
         "seconds_left": max(0, int(r["vote_deadline"] - now)) if r["state"] == "VOTING" else 0,
         "winning_branch": r["winning_branch"] if r["state"] in ("REVEAL", "done") else "",
         "video_url": ""}
    if r["state"] in ("REVEAL", "done") and r["winning_branch"] in ("a", "b"):
        d["video_url"] = r["branch_a_url"] if r["winning_branch"] == "a" else r["branch_b_url"]
    if r["state"] in ("VOTING", "LOCKED", "REVEAL", "done"):
        rows = q_all("SELECT choice, SUM(weight) AS w FROM votes WHERE bout_id=%s AND round_no=%s"
                     " GROUP BY choice", (r["bout_id"], r["round_no"]))
        d["tally"] = {row["choice"]: int(row["w"] or 0) for row in rows}
    return d


def get_state(round_id=None):
    if round_id:
        r = q_one("SELECT * FROM live_rounds WHERE id=%s", (round_id,))
    else:
        r = q_one("SELECT * FROM live_rounds ORDER BY created_at DESC LIMIT 1")
    if not r:
        return 404, {"error": "no live round yet"}
    b = q_one("SELECT fighter_a, fighter_b, title FROM bouts WHERE id=%s", (r["bout_id"],))
    d = public_state(r)
    if b:
        d.update({"fighter_a": b["fighter_a"], "fighter_b": b["fighter_b"],
                  "title": b["title"]})
    return 200, d


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        rid = qs.get("round_id", [None])[0]
        status, d = get_state(rid)
        send(self, status, d)
