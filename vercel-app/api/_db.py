"""Shared DB + response helpers for Vercel Python serverless functions."""
import hashlib
import json as _json
import os
import time

import psycopg
from psycopg.rows import dict_row

ALLOW_ORIGIN = "https://zjutimes2015.github.io"
CHOICES = {"heavy", "dodge", "guard"}
RATE_LIMIT = 20
RATE_WINDOW_S = 60

SCHEMA = """
CREATE TABLE IF NOT EXISTS bouts (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  fighter_a TEXT NOT NULL,
  fighter_b TEXT NOT NULL,
  round_no INTEGER NOT NULL DEFAULT 1,
  voting_open INTEGER NOT NULL DEFAULT 0,
  created_at DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS votes (
  id BIGSERIAL PRIMARY KEY,
  bout_id TEXT NOT NULL,
  round_no INTEGER NOT NULL,
  choice TEXT NOT NULL,
  device_hash TEXT NOT NULL,
  ip TEXT NOT NULL,
  ip_ua TEXT NOT NULL DEFAULT '',
  created_at DOUBLE PRECISION NOT NULL,
  updated_at DOUBLE PRECISION NOT NULL,
  UNIQUE (bout_id, round_no, device_hash)
);
CREATE TABLE IF NOT EXISTS rate_hits (
  ip TEXT NOT NULL,
  ts DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rate_ip_ts ON rate_hits (ip, ts);
CREATE TABLE IF NOT EXISTS fan_captions (
  id BIGSERIAL PRIMARY KEY,
  text TEXT NOT NULL,
  nickname TEXT NOT NULL DEFAULT '匿名拳迷',
  device_hash TEXT NOT NULL DEFAULT '',
  ip TEXT NOT NULL DEFAULT '',
  ip_ua TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  pinned INTEGER NOT NULL DEFAULT 0,
  created_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_captions_status ON fan_captions (status, created_at);
"""

SEED = [
    ("qf1", "QF1 — Sample Bout", "IRON JAW", "VIPER", 2, 1),
    ("qf2", "QF2", "SLEDGE", "MONSOON", 1, 0),
    ("qf3", "QF3", "VOLT", "THE PROFESSOR", 1, 0),
    ("qf4", "QF4", "GOLIATH-7", "LA REINA", 1, 0),
]

_inited = False


def _ensure():
    global _inited
    if _inited:
        return
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL not set")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)
            cur.execute("SELECT COUNT(*) AS n FROM bouts")
            if cur.fetchone()["n"] == 0:
                now = time.time()
                cur.executemany(
                    "INSERT INTO bouts (id,title,fighter_a,fighter_b,round_no,voting_open,created_at)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    [(i, t, a, b, r, o, now) for (i, t, a, b, r, o) in SEED],
                )
        conn.commit()
    _inited = True


def _conn():
    _ensure()
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


def q_all(sql, params=()):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def q_one(sql, params=()):
    rows = q_all(sql, params)
    return rows[0] if rows else None


def q_write(sql, params=()):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rc = cur.rowcount
        conn.commit()
    return rc


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:32]


def check_rate(ip: str) -> bool:
    now = time.time()
    q_write("DELETE FROM rate_hits WHERE ts < %s", (now - RATE_WINDOW_S,))
    row = q_one("SELECT COUNT(*) AS n FROM rate_hits WHERE ip = %s", (ip,))
    if row and row["n"] >= RATE_LIMIT:
        return False
    q_write("INSERT INTO rate_hits (ip, ts) VALUES (%s, %s)", (ip, now))
    return True


def client_ip(h) -> str:
    xff = h.headers.get("x-forwarded-for", "")
    return xff.split(",")[0].strip() if xff else "unknown"


def send(h, status: int, data, cors: bool = True):
    body = _json.dumps(data, ensure_ascii=False).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    if cors:
        h.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        h.send_header("Vary", "Origin")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def send_cors_preflight(h):
    h.send_response(204)
    h.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
    h.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type,X-Admin-Token")
    h.send_header("Access-Control-Max-Age", "86400")
    h.end_headers()


def read_json(h):
    length = int(h.headers.get("Content-Length", 0) or 0)
    raw = h.rfile.read(length) if length else b"{}"
    return _json.loads(raw.decode() or "{}")


def require_admin(h) -> bool:
    return h.headers.get("X-Admin-Token") == os.environ.get("ADMIN_TOKEN")
