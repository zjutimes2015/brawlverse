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
CREATE TABLE IF NOT EXISTS bet_wallets (
  device_hash TEXT PRIMARY KEY,
  balance BIGINT NOT NULL DEFAULT 0,
  last_claim DOUBLE PRECISION NOT NULL DEFAULT 0,
  created_at DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS bet_markets (
  id TEXT PRIMARY KEY,
  bout_id TEXT NOT NULL,
  market_type TEXT NOT NULL,
  question TEXT NOT NULL,
  selections TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  winning_selection TEXT,
  created_at DOUBLE PRECISION NOT NULL,
  settled_at DOUBLE PRECISION
);
CREATE TABLE IF NOT EXISTS bets (
  id BIGSERIAL PRIMARY KEY,
  market_id TEXT NOT NULL,
  device_hash TEXT NOT NULL,
  selection TEXT NOT NULL,
  amount BIGINT NOT NULL,
  ip_ua TEXT NOT NULL DEFAULT '',
  created_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bets_market ON bets (market_id);
CREATE TABLE IF NOT EXISTS bet_ledger (
  id BIGSERIAL PRIMARY KEY,
  device_hash TEXT NOT NULL,
  delta BIGINT NOT NULL,
  reason TEXT NOT NULL,
  ref TEXT NOT NULL DEFAULT '',
  created_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_device ON bet_ledger (device_hash, created_at);
CREATE TABLE IF NOT EXISTS fighter_records (
  fighter TEXT PRIMARY KEY,
  wins INTEGER NOT NULL DEFAULT 0,
  losses INTEGER NOT NULL DEFAULT 0,
  kos INTEGER NOT NULL DEFAULT 0,
  updated_at DOUBLE PRECISION NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ops_gates (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  note TEXT NOT NULL DEFAULT '',
  updated_at DOUBLE PRECISION NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS subscriptions (
  device_hash TEXT PRIMARY KEY,
  tier TEXT NOT NULL DEFAULT 'free',
  status TEXT NOT NULL DEFAULT 'active',
  stripe_customer_id TEXT NOT NULL DEFAULT '',
  stripe_subscription_id TEXT NOT NULL DEFAULT '',
  current_period_end DOUBLE PRECISION NOT NULL DEFAULT 0,
  created_at DOUBLE PRECISION NOT NULL,
  updated_at DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS fantasy_teams (
  id BIGSERIAL PRIMARY KEY,
  device_hash TEXT NOT NULL,
  season TEXT NOT NULL DEFAULT 's1',
  team_name TEXT NOT NULL,
  picks TEXT NOT NULL DEFAULT '[]',
  created_at DOUBLE PRECISION NOT NULL,
  UNIQUE (device_hash, season)
);
CREATE INDEX IF NOT EXISTS idx_fantasy_season ON fantasy_teams (season);
CREATE TABLE IF NOT EXISTS webhook_events (
  event_id TEXT PRIMARY KEY,
  created_at DOUBLE PRECISION NOT NULL
);
"""

GATE_SEED = [
    ("p1-teaser-posted", "P1 预告片已手动发布（三平台+热门BGM）"),
    ("p1-window", "P1 七天验证窗口（发布日起 7 天）"),
    ("p1-kill", "P1 杀线裁决：≥3 条 'when\\'s the fight' 类评论 或 单条 >5k 播放"),
    ("p2-unlocked", "P2 解锁（需 p1-kill 先完成，代码强制）"),
    ("sub-ringside", "订阅 Ringside 开放（门槛：1 万粉）"),
    ("sub-booker", "订阅 Booker/Promoter 开放（门槛：5 万粉）"),
    ("sub-fantasy", "梦幻联赛上线（S2 开赛）"),
]

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
            # additive migrations for DBs created before these columns existed
            cur.execute("ALTER TABLE bouts ADD COLUMN IF NOT EXISTS tactic_note TEXT DEFAULT ''")
            cur.execute("ALTER TABLE bet_markets ADD COLUMN IF NOT EXISTS house_pool TEXT DEFAULT '{}'")
            cur.execute("ALTER TABLE votes ADD COLUMN IF NOT EXISTS weight INTEGER DEFAULT 1")
            cur.execute("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS waffo_subscription_id TEXT DEFAULT ''")
            cur.execute("SELECT COUNT(*) AS n FROM bouts")
            if cur.fetchone()["n"] == 0:
                now = time.time()
                cur.executemany(
                    "INSERT INTO bouts (id,title,fighter_a,fighter_b,round_no,voting_open,created_at)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    [(i, t, a, b, r, o, now) for (i, t, a, b, r, o) in SEED],
                )
            cur.execute("SELECT COUNT(*) AS n FROM ops_gates")
            if cur.fetchone()["n"] == 0:
                cur.executemany(
                    "INSERT INTO ops_gates (id,label,status,updated_at) VALUES (%s,%s,'pending',%s)",
                    [(i, l, time.time()) for (i, l) in GATE_SEED],
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
