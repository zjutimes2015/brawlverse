"""直播回合管理（admin）：建回合 / 填分支 URL / 切状态。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from _db import q_one, q_write, read_json, require_admin, send, send_cors_preflight  # noqa: E402

from http.server import BaseHTTPRequestHandler

STATES = {"scheduled", "VOTING", "LOCKED", "REVEAL", "done"}


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def _guard(self):
        if not require_admin(self):
            send(self, 403, {"error": "admin only"})
            return False
        return True

    def do_POST(self):
        # 建回合：{bout_id, round_no, tactic_a, tactic_b, vote_minutes}
        if not self._guard():
            return
        try:
            v = read_json(self)
        except Exception:
            send(self, 400, {"error": "bad json"})
            return
        bout_id, round_no = v.get("bout_id"), v.get("round_no")
        ta, tb = str(v.get("tactic_a", "")).strip().lower(), str(v.get("tactic_b", "")).strip().lower()
        if not bout_id or not round_no or not ta or not tb or ta == tb:
            send(self, 400, {"error": "bout_id, round_no, two different tactics required"})
            return
        if not q_one("SELECT id FROM bouts WHERE id=%s", (bout_id,)):
            send(self, 404, {"error": "bout not found"})
            return
        rid = "%s-r%s-%d" % (bout_id, round_no, int(time.time()))
        now = time.time()
        q_write("INSERT INTO live_rounds (id,bout_id,round_no,tactic_a,tactic_b,state,created_at)"
                " VALUES (%s,%s,%s,%s,%s,'scheduled',%s)",
                (rid, bout_id, int(round_no), ta, tb, now))
        send(self, 200, {"ok": True, "round_id": rid})

    def do_PATCH(self):
        # {round_id, branch_a_url?, branch_b_url?, state?, vote_minutes?}
        if not self._guard():
            return
        try:
            v = read_json(self)
        except Exception:
            send(self, 400, {"error": "bad json"})
            return
        rid = v.get("round_id")
        r = q_one("SELECT * FROM live_rounds WHERE id=%s", (rid,)) if rid else None
        if not r:
            send(self, 404, {"error": "round not found"})
            return
        sets, params = [], []
        for col in ("branch_a_url", "branch_b_url"):
            if v.get(col) is not None:
                sets.append(col + "=%s")
                params.append(str(v[col])[:500])
        if v.get("state") in STATES:
            sets.append("state=%s")
            params.append(v["state"])
            if v["state"] == "VOTING":
                minutes = float(v.get("vote_minutes", 10))
                sets.append("vote_deadline=%s")
                params.append(time.time() + minutes * 60)
        if not sets:
            send(self, 400, {"error": "nothing to update"})
            return
        params.append(rid)
        q_write("UPDATE live_rounds SET " + ",".join(sets) + " WHERE id=%s", tuple(params))
        send(self, 200, {"ok": True, "round_id": rid})
