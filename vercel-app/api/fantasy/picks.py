import json as _json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from _db import q_one, q_write, read_json, send, send_cors_preflight, sha  # noqa: E402

from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "subscription"))
from _entitlements import FIGHTERS_S1, validate_picks  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_POST(self):
        try:
            v = read_json(self)
        except Exception:
            send(self, 400, {"error": "bad json"})
            return
        device_id = v.get("device_id")
        season = str(v.get("season", "s1")).strip()[:16]
        picks = v.get("picks")
        if not device_id or len(str(device_id)) < 8:
            send(self, 400, {"error": "device_id required"})
            return
        ok, err = validate_picks(picks)
        if not ok:
            send(self, 400, {"error": err})
            return
        picks = [str(p).strip().upper() for p in picks]
        dh = sha(str(device_id))
        team = q_one("SELECT id FROM fantasy_teams WHERE device_hash = %s AND season = %s", (dh, season))
        if not team:
            send(self, 409, {"error": "create a team first (POST /api/fantasy/teams)"})
            return
        q_write("UPDATE fantasy_teams SET picks = %s WHERE device_hash = %s AND season = %s",
                (_json.dumps(picks), dh, season))
        send(self, 200, {"ok": True, "picks": picks, "season": season})
