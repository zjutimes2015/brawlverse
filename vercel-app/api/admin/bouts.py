import os
import sys
import time
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _db import q_write, read_json, require_admin, send, send_cors_preflight

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def _guard(self):
        if not require_admin(self):
            send(self, 403, {"error": "bad admin token"}, cors=False)
            return False
        return True

    def do_POST(self):  # create / replace bout
        if not self._guard():
            return
        try:
            b = read_json(self)
        except Exception:
            send(self, 400, {"error": "bad json"}, cors=False)
            return
        if not all(b.get(k) for k in ("id", "title", "fighter_a", "fighter_b")):
            send(self, 400, {"error": "id,title,fighter_a,fighter_b required"}, cors=False)
            return
        q_write(
            """INSERT INTO bouts (id,title,fighter_a,fighter_b,round_no,voting_open,created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET
                 title=EXCLUDED.title, fighter_a=EXCLUDED.fighter_a,
                 fighter_b=EXCLUDED.fighter_b, round_no=EXCLUDED.round_no,
                 voting_open=EXCLUDED.voting_open""",
            (b["id"], b["title"], b["fighter_a"], b["fighter_b"],
             int(b.get("round_no", 1)), 1 if b.get("voting_open") else 0, time.time()),
        )
        send(self, 200, {"ok": True, "id": b["id"]}, cors=False)

    def do_PATCH(self):  # update bout: /api/admin/bouts?id=qf1
        if not self._guard():
            return
        qs = parse_qs(urlparse(self.path).query)
        bout_id = qs.get("id", [None])[0]
        if not bout_id:
            send(self, 400, {"error": "missing ?id="}, cors=False)
            return
        try:
            p = read_json(self)
        except Exception:
            send(self, 400, {"error": "bad json"}, cors=False)
            return
        sets, vals = [], []
        if "title" in p:
            sets.append("title = %s"); vals.append(p["title"])
        if "round_no" in p:
            sets.append("round_no = %s"); vals.append(int(p["round_no"]))
        if "voting_open" in p:
            sets.append("voting_open = %s"); vals.append(1 if p["voting_open"] else 0)
        if "tactic_note" in p:
            sets.append("tactic_note = %s"); vals.append(str(p["tactic_note"])[:300])
        if not sets:
            send(self, 400, {"error": "nothing to update"}, cors=False)
            return
        vals.append(bout_id)
        rc = q_write(f"UPDATE bouts SET {','.join(sets)} WHERE id = %s", vals)
        if not rc:
            send(self, 404, {"error": "bout not found"}, cors=False)
            return
        send(self, 200, {"ok": True, "id": bout_id}, cors=False)
