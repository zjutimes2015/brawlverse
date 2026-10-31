import json as _json
import os
import sys
import time
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from _db import q_all, q_write, read_json, send, send_cors_preflight, sha  # noqa: E402

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        season = qs.get("season", ["s1"])[0]
        rows = q_all(
            "SELECT team_name, picks, substr(device_hash,1,8) AS player FROM fantasy_teams"
            " WHERE season = %s ORDER BY created_at",
            (season,),
        )
        send(self, 200, {"season": season, "teams": [
            {"team_name": r["team_name"], "picks": _json.loads(r["picks"]), "player": r["player"]}
            for r in rows]})

    def do_POST(self):
        try:
            v = read_json(self)
        except Exception:
            send(self, 400, {"error": "bad json"})
            return
        device_id = v.get("device_id")
        team_name = str(v.get("team_name", "")).strip()[:40]
        season = str(v.get("season", "s1")).strip()[:16]
        if not device_id or len(str(device_id)) < 8:
            send(self, 400, {"error": "device_id required"})
            return
        if not team_name:
            send(self, 400, {"error": "team_name required"})
            return
        dh = sha(str(device_id))
        q_write(
            """INSERT INTO fantasy_teams (device_hash, season, team_name, picks, created_at)
               VALUES (%s,%s,%s,'[]',%s)
               ON CONFLICT (device_hash, season) DO UPDATE SET team_name = EXCLUDED.team_name""",
            (dh, season, team_name, time.time()),
        )
        send(self, 200, {"ok": True, "team_name": team_name, "season": season})
