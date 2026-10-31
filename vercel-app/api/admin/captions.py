import os
import sys
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _db import q_all, q_write, read_json, require_admin, send, send_cors_preflight

from http.server import BaseHTTPRequestHandler

ACTIONS = {"approve", "reject", "pin", "unpin", "delete"}


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def _guard(self):
        if not require_admin(self):
            send(self, 403, {"error": "bad admin token"}, cors=False)
            return False
        return True

    def do_GET(self):  # review queue: ?status=pending
        if not self._guard():
            return
        qs = parse_qs(urlparse(self.path).query)
        status = qs.get("status", ["pending"])[0]
        if status not in ("pending", "approved", "rejected"):
            status = "pending"
        rows = q_all(
            """SELECT id, text, nickname, device_hash, ip, status, pinned, created_at
               FROM fan_captions WHERE status = %s ORDER BY created_at DESC LIMIT 100""",
            (status,),
        )
        send(self, 200, [dict(r) for r in rows], cors=False)

    def do_PATCH(self):  # ?id=  body: {action}
        if not self._guard():
            return
        qs = parse_qs(urlparse(self.path).query)
        cid = qs.get("id", [None])[0]
        if not cid:
            send(self, 400, {"error": "missing ?id="}, cors=False)
            return
        try:
            p = read_json(self)
        except Exception:
            send(self, 400, {"error": "bad json"}, cors=False)
            return
        action = p.get("action")
        if action not in ACTIONS:
            send(self, 400, {"error": "action must be approve|reject|pin|unpin|delete"},
                 cors=False)
            return
        if action == "delete":
            q_write("DELETE FROM fan_captions WHERE id = %s", (cid,))
        elif action == "pin":
            q_write("UPDATE fan_captions SET pinned = 0 WHERE pinned = 1")
            q_write("UPDATE fan_captions SET status='approved', pinned=1 WHERE id = %s", (cid,))
        elif action == "unpin":
            q_write("UPDATE fan_captions SET pinned = 0 WHERE id = %s", (cid,))
        elif action == "approve":
            q_write("UPDATE fan_captions SET status='approved' WHERE id = %s", (cid,))
        else:  # reject
            q_write("UPDATE fan_captions SET status='rejected', pinned=0 WHERE id = %s", (cid,))
        send(self, 200, {"ok": True, "id": cid, "action": action}, cors=False)
