import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _db import send, send_cors_preflight

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_cors_preflight(self)

    def do_GET(self):
        send(self, 200, {"ok": True})
