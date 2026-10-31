"""Stub-DB tests for the betting module. Fakes _db at the query level."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.expanduser("~/workspace/brawlverse/vercel-app/api/betting"))
sys.path.insert(0, os.path.expanduser("~/workspace/brawlverse/vercel-app/api"))

import _db
import _common

# ---- in-memory fake ----
FAKE = {"wallets": {}, "markets": {}, "bets": [], "ledger": []}


def fq_all(sql, params=()):
    if "FROM bet_wallets WHERE device_hash" in sql:
        w = FAKE["wallets"].get(params[0])
        return [w] if w else []
    if "FROM bet_markets WHERE id" in sql:
        m = FAKE["markets"].get(params[0])
        return [m] if m else []
    if "FROM bet_markets" in sql:
        return list(FAKE["markets"].values())
    if "GROUP BY selection" in sql:
        pools = {}
        for b in FAKE["bets"]:
            if b["market_id"] == params[0]:
                pools[b["selection"]] = pools.get(b["selection"], 0) + b["amount"]
        return [{"selection": k, "pool": v} for k, v in pools.items()]
    if "FROM bets WHERE market_id" in sql:
        return [b for b in FAKE["bets"] if b["market_id"] == params[0]]
    if "FROM bet_wallets ORDER BY balance" in sql:
        return sorted(FAKE["wallets"].values(), key=lambda w: -w["balance"])[:20]
    return []


def fq_one(sql, params=()):
    rows = fq_all(sql, params)
    return rows[0] if rows else None


def fq_write(sql, params=()):
    if sql.startswith("INSERT INTO bet_wallets"):
        FAKE["wallets"][params[0]] = {"device_hash": params[0], "balance": params[1],
                                      "last_claim": params[2], "created_at": params[3]}
    elif sql.startswith("INSERT INTO bet_ledger"):
        FAKE["ledger"].append({"device_hash": params[0], "delta": params[1],
                               "reason": params[2], "ref": params[3]})
    elif sql.startswith("INSERT INTO bet_markets"):
        FAKE["markets"][params[0]] = {"id": params[0], "bout_id": params[1], "market_type": params[2],
                                      "question": params[3], "selections": params[4],
                                      "status": "open", "winning_selection": None}
    elif sql.startswith("INSERT INTO bets"):
        FAKE["bets"].append({"market_id": params[0], "device_hash": params[1],
                             "selection": params[2], "amount": params[3]})
    elif sql.startswith("UPDATE bet_wallets SET balance = balance -"):
        FAKE["wallets"][params[1]]["balance"] -= params[0]
    elif "last_claim" in sql and sql.startswith("UPDATE bet_wallets"):
        w = FAKE["wallets"][params[2]]
        w["balance"] += params[0]
        w["last_claim"] = params[1]
    elif sql.startswith("UPDATE bet_wallets SET balance = balance +"):
        FAKE["wallets"][params[1]]["balance"] += params[0]
    elif sql.startswith("UPDATE bet_markets SET status='locked'"):
        FAKE["markets"][params[0]]["status"] = "locked"
    elif sql.startswith("UPDATE bet_markets SET status='settled'"):
        m = FAKE["markets"][params[2]]
        m["status"] = "settled"
        m["winning_selection"] = params[0]
        m["settled_at"] = params[1]
    return 1


_db.q_all = fq_all
_db.q_one = fq_one
_db.q_write = fq_write
_common.q_all = fq_all
_common.q_one = fq_one
_common.q_write = fq_write

passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print("PASS", name)
    else:
        failed += 1
        print("FAIL", name)


# 1. 新钱包注册送 1000
w = _common.get_wallet("devA")
check("signup bonus 1000", w["balance"] == 1000)
check("ledger signup", any(e["reason"] == "signup" for e in FAKE["ledger"]))

# 2. 开盘
fq_write("INSERT INTO bet_markets (id, bout_id, market_type, question, selections, status, created_at)",
         ("qf1-winner", "qf1", "winner", "Who wins QF1?", json.dumps(["IRON JAW", "VIPER"]), time.time()))
check("market created", "qf1-winner" in FAKE["markets"])

# 3. 下注扣款
dh_a, dh_b = _common.sha("device-alice-001"), _common.sha("device-bob-002")
_common.get_wallet(dh_a)
_common.get_wallet(dh_b)
# simulate bet.py core: deduct + insert
for dh, sel, amt in [(dh_a, "IRON JAW", 700), (dh_b, "VIPER", 300)]:
    fq_write("UPDATE bet_wallets SET balance = balance - %s WHERE device_hash = %s", (amt, dh))
    fq_write("INSERT INTO bets (market_id, device_hash, selection, amount, ip_ua, created_at)",
             ("qf1-winner", dh, sel, amt, "x", time.time()))
check("alice balance 300", FAKE["wallets"][dh_a]["balance"] == 300)
check("bob balance 700", FAKE["wallets"][dh_b]["balance"] == 700)

# 4. 彩池与隐含赔率
pools = _common.pool_totals("qf1-winner")
check("pools", pools == {"IRON JAW": 700, "VIPER": 300})

# 5. 结算：VIPER 赢，总池 1000，VIPER 池 300 → bob 得 floor(300*1000/300)=1000
res = _common.settle_market("qf1-winner", "VIPER")
check("settle returns", res is not None and res["total_pool"] == 1000 and res["win_pool"] == 300)
check("bob payout 1000", FAKE["wallets"][dh_b]["balance"] == 700 + 1000)
check("alice stays 300", FAKE["wallets"][dh_a]["balance"] == 300)
check("market settled", FAKE["markets"]["qf1-winner"]["status"] == "settled")
check("ledger bet_won", any(e["reason"] == "bet_won" and e["delta"] == 1000 for e in FAKE["ledger"]))

# 6. 重复结算被拒绝
check("double settle -> None", _common.settle_market("qf1-winner", "VIPER") is None)

# 7. 无人押中：全退彩池不赔付
fq_write("INSERT INTO bet_markets (id, bout_id, market_type, question, selections, status, created_at)",
         ("qf2-winner", "qf2", "winner", "Who wins QF2?", json.dumps(["SLEDGE", "MONSOON"]), time.time()))
fq_write("INSERT INTO bets (market_id, device_hash, selection, amount, ip_ua, created_at)",
         ("qf2-winner", dh_a, "SLEDGE", 100, "x", time.time()))
res2 = _common.settle_market("qf2-winner", "MONSOON")
check("no winner pool -> win_pool 0", res2 is not None and res2["win_pool"] == 0 and res2["payouts"] == [])
check("void ledger", any(e["reason"] == "bet_void" for e in FAKE["ledger"]))

# 8. 每日领取
w0 = _common.get_wallet(dh_a)["balance"]
# claim.py core
now = time.time()
FAKE["wallets"][dh_a]["last_claim"] = 0
fq_write("UPDATE bet_wallets SET balance = balance + %s, last_claim = %s WHERE device_hash = %s",
         (_common.DAILY_CLAIM, now, dh_a))
check("daily +100", FAKE["wallets"][dh_a]["balance"] == w0 + 100)

# 9. 非法选项结算被拒绝
fq_write("INSERT INTO bet_markets (id, bout_id, market_type, question, selections, status, created_at)",
         ("qf3-winner", "qf3", "winner", "Who wins QF3?", json.dumps(["VOLT", "THE PROFESSOR"]), time.time()))
check("bad selection -> None", _common.settle_market("qf3-winner", "BATMAN") is None)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
