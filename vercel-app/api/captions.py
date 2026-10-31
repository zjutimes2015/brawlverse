import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _db import (check_rate, client_ip, q_write, read_json, send,
                 send_cors_preflight, sha)

from http.server import BaseHTTPRequestHandler

# keyword pre-screen: obvious spam/scam/profanity -> auto-reject.
# Final say belongs to the human booker in /admin.html.
BLOCK_RE = re.compile(
    r"加微信|微信号|兼职|贷款|赌博|博彩|六合彩|时时彩|代购|客服|代理|日结|赚钱|"
    r"http|www\.|\.com|\.cn|fuck|shit|bitch|asshole|damn",
    re.I,
)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_POST(self):
        try:
            v = read_json(self)
        except Exception:
            send(self, 400, {"error": "bad json"})
            return
        text = str(v.get("text", "")).strip()
        if not text or len(text) > 40:
            send(self, 400, {"error": "text required, max 40 chars"})
            return
        nickname = str(v.get("nickname", "")).strip()[:12] or "匿名拳迷"
        device_id = str(v.get("device_id", ""))
        if len(device_id) < 8:
            send(self, 400, {"error": "device_id required"})
            return
        ip = client_ip(self)
        if not check_rate(ip):
            send(self, 429, {"error": "rate limited: slow down"})
            return
        ua = self.headers.get("User-Agent", "")
        status = "rejected" if BLOCK_RE.search(text) else "pending"
        q_write(
            """INSERT INTO fan_captions
               (text, nickname, device_hash, ip, ip_ua, status, pinned, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,0,%s)""",
            (text, nickname, sha(device_id), ip, sha(ip + "|" + ua), status, time.time()),
        )
        send(self, 200, {"ok": True, "status": status,
                         "msg": "已提交，待精选！" if status == "pending" else "内容未通过初筛"})
