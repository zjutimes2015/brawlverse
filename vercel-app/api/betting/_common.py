"""Betting helpers: parimutuel pools, wallets, ledger. Play-money only."""
import json as _json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from _db import q_all, q_one, q_write, sha  # noqa: E402

SIGNUP_BONUS = 1000
DAILY_CLAIM = 100
DAY_S = 86400
MAX_BET = 100000


def get_wallet(dh: str):
    w = q_one("SELECT * FROM bet_wallets WHERE device_hash = %s", (dh,))
    if w:
        return w
    now = time.time()
    q_write(
        "INSERT INTO bet_wallets (device_hash, balance, last_claim, created_at) VALUES (%s,%s,%s,%s)",
        (dh, SIGNUP_BONUS, 0, now),
    )
    q_write(
        "INSERT INTO bet_ledger (device_hash, delta, reason, ref, created_at) VALUES (%s,%s,%s,%s,%s)",
        (dh, SIGNUP_BONUS, "signup", "", now),
    )
    return q_one("SELECT * FROM bet_wallets WHERE device_hash = %s", (dh,))


def pool_totals(market_id: str):
    rows = q_all(
        "SELECT selection, COALESCE(SUM(amount),0) AS pool FROM bets WHERE market_id = %s GROUP BY selection",
        (market_id,),
    )
    pools = {r["selection"]: int(r["pool"]) for r in rows}
    m = q_one("SELECT house_pool FROM bet_markets WHERE id = %s", (market_id,))
    if m and m.get("house_pool"):
        try:
            for s, amt in _json.loads(m["house_pool"]).items():
                pools[s] = pools.get(s, 0) + int(amt)
        except Exception:
            pass
    return pools


def _bump_record(fighter: str, won: bool, ko: bool):
    now = time.time()
    q_write(
        """INSERT INTO fighter_records (fighter, wins, losses, kos, updated_at)
           VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT (fighter) DO UPDATE SET
             wins = fighter_records.wins + %s,
             losses = fighter_records.losses + %s,
             kos = fighter_records.kos + %s,
             updated_at = %s""",
        (fighter, 1 if won else 0, 0 if won else 1, 1 if (won and ko) else 0, now,
         1 if won else 0, 0 if won else 1, 1 if (won and ko) else 0, now),
    )


def market_view(m):
    sels = _json.loads(m["selections"])
    pools = pool_totals(m["id"])
    total = sum(pools.values())
    odds = {}
    for s in sels:
        p = pools.get(s, 0)
        odds[s] = round(total / p, 2) if p > 0 else None
    return {
        "id": m["id"],
        "bout_id": m["bout_id"],
        "market_type": m["market_type"],
        "question": m["question"],
        "selections": sels,
        "status": m["status"],
        "pools": pools,
        "total_pool": total,
        "implied_odds": odds,
        "winning_selection": m["winning_selection"],
    }


def settle_market(market_id: str, winning_selection: str):
    """Parimutuel payout. Returns (total_pool, win_pool, payouts)."""
    m = q_one("SELECT * FROM bet_markets WHERE id = %s", (market_id,))
    if not m or m["status"] == "settled":
        return None
    sels = _json.loads(m["selections"])
    if winning_selection not in sels:
        return None
    bets = q_all("SELECT * FROM bets WHERE market_id = %s", (market_id,))
    total = sum(b["amount"] for b in bets)
    win_bets = [b for b in bets if b["selection"] == winning_selection]
    win_pool = sum(b["amount"] for b in win_bets)
    now = time.time()
    payouts = []
    if win_pool > 0:
        for b in win_bets:
            payout = (b["amount"] * total) // win_pool
            q_write(
                "UPDATE bet_wallets SET balance = balance + %s WHERE device_hash = %s",
                (payout, b["device_hash"]),
            )
            q_write(
                "INSERT INTO bet_ledger (device_hash, delta, reason, ref, created_at)"
                " VALUES (%s,%s,%s,%s,%s)",
                (b["device_hash"], payout, "bet_won", market_id, now),
            )
            payouts.append({"device": b["device_hash"][:8], "payout": payout})
    else:
        for b in bets:
            q_write(
                "INSERT INTO bet_ledger (device_hash, delta, reason, ref, created_at)"
                " VALUES (%s,%s,%s,%s,%s)",
                (b["device_hash"], 0, "bet_void", market_id, now),
            )
    q_write(
        "UPDATE bet_markets SET status='settled', winning_selection=%s, settled_at=%s WHERE id=%s",
        (winning_selection, now, market_id),
    )
    # legacy ledger: winner-market settle writes permanent fighter records
    if m["market_type"] == "winner":
        bout = q_one("SELECT fighter_a, fighter_b FROM bouts WHERE id = %s", (m["bout_id"],))
        if bout and winning_selection in (bout["fighter_a"], bout["fighter_b"]):
            loser = bout["fighter_b"] if winning_selection == bout["fighter_a"] else bout["fighter_a"]
            method = q_one(
                "SELECT winning_selection FROM bet_markets"
                " WHERE bout_id = %s AND market_type = 'method' AND status = 'settled'"
                " ORDER BY settled_at DESC LIMIT 1",
                (m["bout_id"],),
            )
            ko = bool(method and str(method["winning_selection"]).upper() == "KO")
            _bump_record(winning_selection, True, ko)
            _bump_record(loser, False, False)
    return {"total_pool": total, "win_pool": win_pool, "payouts": payouts}
