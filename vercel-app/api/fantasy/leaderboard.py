import json as _json
import os
import sys
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from _db import q_all, send, send_cors_preflight  # noqa: E402

from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "subscription"))
from _entitlements import fantasy_score  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        season = qs.get("season", ["s1"])[0]
        teams = q_all(
            "SELECT team_name, picks, substr(device_hash,1,8) AS player FROM fantasy_teams WHERE season = %s",
            (season,),
        )
        recs = {r["fighter"].upper(): r for r in
                q_all("SELECT fighter, wins, kos FROM fighter_records")}
        board = []
        for t in teams:
            picks = _json.loads(t["picks"])
            board.append({"team_name": t["team_name"], "player": t["player"],
                          "picks": picks, "score": fantasy_score(picks, recs)})
        board.sort(key=lambda x: -x["score"])
        for i, b in enumerate(board):
            b["rank"] = i + 1
        send(self, 200, {"season": season, "leaderboard": board,
                         "scoring": "win=3, KO win=5, loss=0"})
