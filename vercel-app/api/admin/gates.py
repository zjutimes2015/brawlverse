import os
import sys
import time
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _db import q_all, q_one, q_write, read_json, require_admin, send, send_cors_preflight

from http.server import BaseHTTPRequestHandler

# p2-unlocked is code-blocked until p1-kill is done: the kill line lives in the
# database, not in someone's memory.
GUARD = {"p2-unlocked": "p1-kill"}


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def _auth(self):
        if not require_admin(self):
            send(self, 403, {"error": "forbidden"}, cors=False)
            return False
        return True

    def do_GET(self):
        if not self._auth():
            return
        rows = q_all("SELECT id, label, status, note FROM ops_gates ORDER BY id")
        send(self, 200, {"gates": [dict(r) for r in rows]}, cors=False)

    def do_PATCH(self):
        if not self._auth():
            return
        qs = parse_qs(urlparse(self.path).query)
        gid = qs.get("id", [None])[0]
        if not gid:
            send(self, 400, {"error": "missing ?id="}, cors=False)
            return
        try:
            p = read_json(self)
        except Exception:
            p = {}
        status = str(p.get("status", "")).strip()
        note = str(p.get("note", ""))[:500]
        if status not in ("pending", "done", "killed"):
            send(self, 400, {"error": "status must be pending|done|killed"}, cors=False)
            return
        if status == "done" and gid in GUARD:
            dep = q_one("SELECT status FROM ops_gates WHERE id = %s", (GUARD[gid],))
            if not dep or dep["status"] != "done":
                send(self, 409, {"error": "blocked: %s must be done first" % GUARD[gid]}, cors=False)
                return
        rc = q_write("UPDATE ops_gates SET status=%s, note=%s, updated_at=%s WHERE id=%s",
                     (status, note, time.time(), gid))
        if not rc:
            send(self, 404, {"error": "gate not found"}, cors=False)
            return
        send(self, 200, {"ok": True, "id": gid, "status": status}, cors=False)
