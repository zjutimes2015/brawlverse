"""
BRAWLVERSE P2-full backend — tactics voting API + booker admin.
Stack: FastAPI + SQLite (stdlib). Run: uvicorn app:app --host 0.0.0.0 --port 8000
Anti-fraud v1 (honest level): one vote per device per round (change = update),
per-IP rate limit, device id hashed server-side. No real fingerprinting yet.
"""
import hashlib
import os
import sqlite3
import time
from contextlib import contextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "brawlverse.db"))
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "change-me")
RATE_LIMIT = 20          # votes per IP per window
RATE_WINDOW = 60         # seconds

CHOICES = {"heavy", "dodge", "guard"}

app = FastAPI(title="BRAWLVERSE API", version="2.0")
_hits: dict[str, list[float]] = {}


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS bouts (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                fighter_a TEXT NOT NULL,
                fighter_b TEXT NOT NULL,
                round_no INTEGER NOT NULL DEFAULT 1,
                voting_open INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bout_id TEXT NOT NULL,
                round_no INTEGER NOT NULL,
                choice TEXT NOT NULL,
                device_hash TEXT NOT NULL,
                ip TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE (bout_id, round_no, device_hash)
            );
            """
        )
        # seed Season 1 quarterfinals if empty
        if c.execute("SELECT COUNT(*) AS n FROM bouts").fetchone()["n"] == 0:
            now = time.time()
            c.executemany(
                "INSERT INTO bouts (id, title, fighter_a, fighter_b, round_no, voting_open, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    ("qf1", "QF1 — Sample Bout", "IRON JAW", "VIPER", 2, 1, now),
                    ("qf2", "QF2", "SLEDGE", "MONSOON", 1, 0, now),
                    ("qf3", "QF3", "VOLT", "THE PROFESSOR", 1, 0, now),
                    ("qf4", "QF4", "GOLIATH-7", "LA REINA", 1, 0, now),
                ],
            )


init_db()


def check_rate(ip: str):
    now = time.time()
    hits = [t for t in _hits.get(ip, []) if now - t < RATE_WINDOW]
    if len(hits) >= RATE_LIMIT:
        raise HTTPException(429, "rate limited: slow down")
    hits.append(now)
    _hits[ip] = hits


def require_admin(token: str | None):
    if token != ADMIN_TOKEN:
        raise HTTPException(403, "bad admin token")


class VoteIn(BaseModel):
    bout_id: str = Field(min_length=1, max_length=32)
    round_no: int = Field(ge=1, le=12)
    choice: str
    device_id: str = Field(min_length=8, max_length=128)


class BoutIn(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=120)
    fighter_a: str = Field(min_length=1, max_length=64)
    fighter_b: str = Field(min_length=1, max_length=64)
    round_no: int = Field(ge=1, le=12, default=1)
    voting_open: bool = False


class BoutPatch(BaseModel):
    title: str | None = None
    round_no: int | None = None
    voting_open: bool | None = None


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/bouts")
def list_bouts():
    with db() as c:
        rows = c.execute("SELECT * FROM bouts ORDER BY created_at").fetchall()
    return [
        {
            "id": r["id"], "title": r["title"],
            "fighter_a": r["fighter_a"], "fighter_b": r["fighter_b"],
            "round_no": r["round_no"], "voting_open": bool(r["voting_open"]),
        }
        for r in rows
    ]


@app.post("/api/votes")
def cast_vote(v: VoteIn, request: Request):
    choice = v.choice.strip().lower()
    if choice not in CHOICES:
        raise HTTPException(400, f"choice must be one of {sorted(CHOICES)}")
    ip = request.client.host if request.client else "unknown"
    check_rate(ip)
    with db() as c:
        bout = c.execute("SELECT * FROM bouts WHERE id = ?", (v.bout_id,)).fetchone()
        if not bout:
            raise HTTPException(404, "bout not found")
        if not bout["voting_open"]:
            raise HTTPException(409, "voting is closed for this bout")
        device_hash = hashlib.sha256(v.device_id.encode()).hexdigest()[:32]
        now = time.time()
        c.execute(
            """INSERT INTO votes (bout_id, round_no, choice, device_hash, ip, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (bout_id, round_no, device_hash)
               DO UPDATE SET choice = excluded.choice, updated_at = excluded.updated_at""",
            (v.bout_id, v.round_no, choice, device_hash, ip, now, now),
        )
    return {"ok": True, "bout_id": v.bout_id, "round_no": v.round_no, "choice": choice}


@app.get("/api/votes/tally")
def tally(bout_id: str, round_no: int = 1):
    with db() as c:
        rows = c.execute(
            "SELECT choice, COUNT(*) AS n FROM votes WHERE bout_id = ? AND round_no = ? GROUP BY choice",
            (bout_id, round_no),
        ).fetchall()
    result = {ch: 0 for ch in CHOICES}
    for r in rows:
        result[r["choice"]] = r["n"]
    return {"bout_id": bout_id, "round_no": round_no, "tally": result,
            "total": sum(result.values())}


# ---- booker admin ----
@app.get("/api/admin/votes")
def admin_votes(bout_id: str | None = None, x_admin_token: str | None = Header(None)):
    require_admin(x_admin_token)
    with db() as c:
        if bout_id:
            rows = c.execute(
                "SELECT * FROM votes WHERE bout_id = ? ORDER BY updated_at DESC LIMIT 500",
                (bout_id,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM votes ORDER BY updated_at DESC LIMIT 500").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/admin/bouts")
def admin_create_bout(b: BoutIn, x_admin_token: str | None = Header(None)):
    require_admin(x_admin_token)
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO bouts (id, title, fighter_a, fighter_b, round_no, voting_open, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (b.id, b.title, b.fighter_a, b.fighter_b, b.round_no, int(b.voting_open), time.time()),
        )
    return {"ok": True, "id": b.id}


@app.patch("/api/admin/bouts/{bout_id}")
def admin_patch_bout(bout_id: str, p: BoutPatch, x_admin_token: str | None = Header(None)):
    require_admin(x_admin_token)
    fields, vals = [], []
    if p.title is not None:
        fields.append("title = ?"); vals.append(p.title)
    if p.round_no is not None:
        fields.append("round_no = ?"); vals.append(p.round_no)
    if p.voting_open is not None:
        fields.append("voting_open = ?"); vals.append(int(p.voting_open))
    if not fields:
        raise HTTPException(400, "nothing to update")
    vals.append(bout_id)
    with db() as c:
        cur = c.execute(f"UPDATE bouts SET {', '.join(fields)} WHERE id = ?", vals)
        if cur.rowcount == 0:
            raise HTTPException(404, "bout not found")
    return {"ok": True, "id": bout_id}


app.mount("/admin", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"),
                               html=True), name="admin")
