"""Tests for subscription tiers, entitlements, fantasy scoring/picks. Stub-DB."""
import os
import sys
import time

sys.path.insert(0, os.path.expanduser("~/workspace/brawlverse/vercel-app/api/subscription"))
sys.path.insert(0, os.path.expanduser("~/workspace/brawlverse/vercel-app/api"))

import _db
import _entitlements as E

passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print("PASS", name)
    else:
        failed += 1
        print("FAIL", name)


# ---- 1. tier table shape ----
check("4 tiers", set(E.TIERS) == {"free", "ringside", "booker", "promoter"})
check("paid tiers", set(E.PAID_TIERS) == {"ringside", "booker", "promoter"})
check("prices", E.TIERS["ringside"]["price_monthly"] == 4.99
      and E.TIERS["booker"]["price_monthly"] == 14.99
      and E.TIERS["promoter"]["price_monthly"] == 49.00
      and E.TIERS["free"]["price_monthly"] == 0)
KEYS = set(E.TIERS["free"])
check("entitlement keys consistent", all(set(v) == KEYS for v in E.TIERS.values()))
check("vote weights escalate",
      E.TIERS["free"]["vote_weight"] < E.TIERS["ringside"]["vote_weight"]
      < E.TIERS["booker"]["vote_weight"] < E.TIERS["promoter"]["vote_weight"])
check("8 fighters S1", len(E.FIGHTERS_S1) == 8)

# ---- 2. fantasy_score ----
recs = {"VIPER": {"wins": 2, "kos": 1}, "IRON JAW": {"wins": 1, "kos": 0},
        "SLEDGE": {"wins": 0, "kos": 0}}
check("ko win=5", E.fantasy_score(["VIPER"], recs) == 5)
check("decision win=3", E.fantasy_score(["IRON JAW"], recs) == 3)
check("loss=0", E.fantasy_score(["SLEDGE"], recs) == 0)
check("sum", E.fantasy_score(["VIPER", "IRON JAW", "SLEDGE"], recs) == 8)
check("unknown=0", E.fantasy_score(["NOBODY"], recs) == 0)

# ---- 3. validate_picks ----
ok, _ = E.validate_picks(["VIPER", "IRON JAW", "VOLT"])
check("valid picks", ok)
ok, _ = E.validate_picks(["viper", "iron jaw", "volt"])
check("case-insensitive", ok)
ok, e = E.validate_picks(["VIPER", "VIPER", "VOLT"])
check("dup rejected", not ok and "distinct" in e)
ok, e = E.validate_picks(["VIPER", "VOLT"])
check("not-3 rejected", not ok)
ok, e = E.validate_picks(["VIPER", "VOLT", "BATMAN"])
check("unknown fighter rejected", not ok and "BATMAN" in e)
ok, _ = E.validate_picks("VIPER")
check("non-list rejected", not ok)

# ---- 4. get_tier with fake DB ----
SUBS = {}


def fq_one(sql, params=()):
    if "FROM subscriptions" in sql:
        return SUBS.get(params[0])
    return None


_db.q_one = fq_one
E.q_one = fq_one  # _entitlements did `from _db import q_one`; patch its binding too
now = time.time()
SUBS["dh_none"] = None
check("no row -> free", E.get_tier("dh_none") == "free")
SUBS["dh_paid"] = {"tier": "booker", "status": "active", "current_period_end": now + 9999}
check("active -> booker", E.get_tier("dh_paid") == "booker")
SUBS["dh_cx"] = {"tier": "promoter", "status": "canceled", "current_period_end": now - 10}
check("canceled past end -> free", E.get_tier("dh_cx") == "free")
SUBS["dh_pd"] = {"tier": "ringside", "status": "past_due", "current_period_end": now + 9999}
check("past_due within period -> ringside", E.get_tier("dh_pd") == "ringside")

# ---- 5. entitlements wiring ----
e = E.entitlements("dh_paid")
check("entitlements tier", e["tier"] == "booker" and e["vote_weight"] == 10)
e = E.entitlements("dh_none")
check("free entitlements", e["tier"] == "free" and e["vote_weight"] == 1
      and not e["early_access"])

# ---- 6. stripe_price_id without env ----
for k in ("STRIPE_PRICE_RINGSIDE", "STRIPE_PRICE_BOOKER", "STRIPE_PRICE_PROMOTER"):
    os.environ.pop(k, None)
check("price id empty without env", E.stripe_price_id("ringside") == "")
os.environ["STRIPE_PRICE_RINGSIDE"] = "price_test123"
check("price id from env", E.stripe_price_id("ringside") == "price_test123")
os.environ.pop("STRIPE_PRICE_RINGSIDE", None)

print("---\n%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
