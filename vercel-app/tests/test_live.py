"""Stub-DB tests for the Friday Fight Night live module. Fakes _db at the query level."""
import os
import sys
import time

LIVE = os.path.expanduser("~/workspace/brawlverse/vercel-app/api/live")
API = os.path.expanduser("~/workspace/brawlverse/vercel-app/api")
sys.path.insert(0, LIVE)
sys.path.insert(0, API)
sys.path.insert(0, os.path.join(API, "subscription"))

import state as live_state
import vote as live_vote
import tally as live_tally

# ---- in-memory fake ----
FAKE = {"rounds": {}, "votes": [], "bouts": {
    "qf1": {"id": "qf1", "title": "QF1", "fighter_a": "IRON JAW", "fighter_b": "VIPER"}}}


def mkround(rid="r1", state="VOTING", ta="heavy", tb="dodge", deadline=None):
    FAKE["rounds"][rid] = {
        "id": rid, "bout_id": "qf1", "round_no": 1,
        "tactic_a": ta, "tactic_b": tb,
        "branch_a_url": "https://cdn/x/a.mp4", "branch_b_url": "https://cdn/x/b.mp4",
        "winning_branch": "", "state": state,
        "vote_deadline": deadline if deadline is not None else time.time() + 600,
        "created_at": time.time()}


def fq_all(sql, params=()):
    if "FROM live_rounds ORDER BY created_at DESC" in sql:
        rs = sorted(FAKE["rounds"].values(), key=lambda r: -r["created_at"])
        return rs[:1]
    if "FROM live_rounds WHERE id" in sql:
        r = FAKE["rounds"].get(params[0])
        return [r] if r else []
    if "FROM bouts WHERE id" in sql:
        b = FAKE["bouts"].get(params[0])
        return [b] if b else []
    if "GROUP BY choice" in sql:
        pools = {}
        for v in FAKE["votes"]:
            if v["bout_id"] == params[0] and v["round_no"] == params[1]:
                pools[v["choice"]] = pools.get(v["choice"], 0) + v["weight"]
        return [{"choice": k, "w": v} for k, v in pools.items()]
    return []


def fq_one(sql, params=()):
    rows = fq_all(sql, params)
    return rows[0] if rows else None


def fq_write(sql, params=()):
    if sql.startswith("INSERT INTO votes"):
        FAKE["votes"].append({"bout_id": params[0], "round_no": params[1], "choice": params[2],
                              "device_hash": params[3], "weight": params[6]})
    elif sql.startswith("UPDATE live_rounds SET winning_branch"):
        FAKE["rounds"][params[1]]["winning_branch"] = params[0]
        FAKE["rounds"][params[1]]["state"] = "REVEAL"
    return 1


for mod in (live_state, live_vote, live_tally):
    mod.q_all = fq_all
    mod.q_one = fq_one
    mod.q_write = fq_write
live_vote.check_rate = lambda ip: True
live_vote.sha = lambda s: "dh-" + s  # deterministic, keeps device_id suffix visible
live_vote.entitlements = lambda dh: {"vote_weight": 3 if dh.endswith("vip") else 1}

passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print("PASS", name)
    else:
        failed += 1
        print("FAIL", name)


# 1. state：VOTING 时隐藏分支 URL，露出倒计时和 tally
mkround("r1", "VOTING")
FAKE["votes"] = [{"bout_id": "qf1", "round_no": 1, "choice": "heavy", "weight": 3}]
s, d = live_state.get_state("r1")
check("state 200", s == 200)
check("state hides video_url in VOTING", d["video_url"] == "")
check("state hides winning_branch in VOTING", d["winning_branch"] == "")
check("state countdown > 0", d["seconds_left"] > 0)
check("state tally weighted", d["tally"].get("heavy") == 3)
check("state has fighters", d["fighter_a"] == "IRON JAW")

# 2. vote：非 VOTING 拒绝
mkround("r2", "LOCKED")
s, d = live_vote.cast_live_vote("r2", "heavy", "device-12345678", "1.2.3.4", "ua")
check("vote 409 when not VOTING", s == 409)

# 3. vote：过期拒绝
mkround("r3", "VOTING", deadline=time.time() - 1)
s, d = live_vote.cast_live_vote("r3", "heavy", "device-12345678", "1.2.3.4", "ua")
check("vote 409 when expired", s == 409)

# 4. vote：非法选项拒绝
mkround("r4", "VOTING")
s, d = live_vote.cast_live_vote("r4", "uppercut", "device-12345678", "1.2.3.4", "ua")
check("vote 400 on bad choice", s == 400)

# 5. vote：正常投票带权重
s, d = live_vote.cast_live_vote("r4", "dodge", "device-12345678vip", "1.2.3.4", "ua")
check("vote 200 ok", s == 200 and d["choice"] == "dodge")
check("vote weight applied", d["weight"] == 3)

# 6. tally：加权多者胜
mkround("r5", "VOTING")
FAKE["votes"] = [
    {"bout_id": "qf1", "round_no": 1, "choice": "heavy", "weight": 3},
    {"bout_id": "qf1", "round_no": 1, "choice": "dodge", "weight": 10},
]
s, d = live_tally.settle_round("r5")
check("tally 200", s == 200)
check("tally winner is b (weighted)", d["winning_branch"] == "b")
check("tally reveals winner url only", d["video_url"] == "https://cdn/x/b.mp4")
check("tally sets REVEAL", FAKE["rounds"]["r5"]["state"] == "REVEAL")

# 7. tally：平票 → a（确定性）
mkround("r6", "VOTING")
FAKE["votes"] = [
    {"bout_id": "qf1", "round_no": 1, "choice": "heavy", "weight": 5},
    {"bout_id": "qf1", "round_no": 1, "choice": "dodge", "weight": 5},
]
s, d = live_tally.settle_round("r6")
check("tally tie -> a", d["winning_branch"] == "a")

# 8. tally：已结算不能重复
s, d = live_tally.settle_round("r6")
check("tally 409 when not awaiting", s == 409)

# 9. tally：不存在的回合
s, d = live_tally.settle_round("nope")
check("tally 404 unknown round", s == 404)

# 10. state：REVEAL 后露出胜者视频
s, d = live_state.get_state("r5")
check("state reveals video in REVEAL", d["video_url"] == "https://cdn/x/b.mp4")
check("state reveals winning_branch", d["winning_branch"] == "b")

# 11. state：无回合时 404
FAKE["rounds"] = {}
s, d = live_state.get_state()
check("state 404 when empty", s == 404)

print("passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
