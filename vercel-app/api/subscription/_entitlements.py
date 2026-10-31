"""Subscription tiers + entitlements. Pure logic; Stripe wiring lives in checkout/webhook."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from _db import q_one  # noqa: E402

# tier -> entitlements. Marginal cost of every entitlement is ~0 (DB flags +
# existing content windows). That is the whole leverage of the model.
TIERS = {
    "free": {
        "vote_weight": 1, "bet_max_mult": 1, "daily_mult": 1,
        "prop_create": False, "stable_create": False, "early_access": False,
        "led_name": False, "booker_night": False, "fantasy": True,
        "price_monthly": 0,
    },
    "ringside": {
        "vote_weight": 3, "bet_max_mult": 2, "daily_mult": 2,
        "prop_create": False, "stable_create": False, "early_access": True,
        "led_name": True, "booker_night": False, "fantasy": True,
        "price_monthly": 4.99,
    },
    "booker": {
        "vote_weight": 10, "bet_max_mult": 5, "daily_mult": 5,
        "prop_create": True, "stable_create": True, "early_access": True,
        "led_name": True, "booker_night": False, "fantasy": True,
        "price_monthly": 14.99,
    },
    "promoter": {
        "vote_weight": 20, "bet_max_mult": 10, "daily_mult": 10,
        "prop_create": True, "stable_create": True, "early_access": True,
        "led_name": True, "booker_night": True, "fantasy": True,
        "price_monthly": 49.00,
    },
}

PAID_TIERS = ("ringside", "booker", "promoter")
PRICE_ENV = {
    "ringside": "STRIPE_PRICE_RINGSIDE",
    "booker": "STRIPE_PRICE_BOOKER",
    "promoter": "STRIPE_PRICE_PROMOTER",
}

FIGHTERS_S1 = ["IRON JAW", "VIPER", "SLEDGE", "MONSOON",
               "VOLT", "THE PROFESSOR", "GOLIATH-7", "LA REINA"]


def get_tier(device_hash: str) -> str:
    """Active paid tier, else free. Past-due/canceled past period end -> free."""
    s = q_one("SELECT tier, status, current_period_end FROM subscriptions WHERE device_hash = %s",
              (device_hash,))
    if not s or s["tier"] not in PAID_TIERS:
        return "free"
    if s["status"] in ("canceled", "past_due") and s["current_period_end"] < time.time():
        return "free"
    return s["tier"]


def entitlements(device_hash: str) -> dict:
    tier = get_tier(device_hash)
    e = dict(TIERS[tier])
    e["tier"] = tier
    return e


def stripe_price_id(tier: str):
    return os.environ.get(PRICE_ENV.get(tier, ""), "")


def fantasy_score(picks, records) -> int:
    """Pure scoring: win=3, KO win=5, loss=0. records: {fighter: {wins, kos}}."""
    total = 0
    for f in picks:
        r = records.get(f.upper(), {})
        if r.get("wins", 0) > 0:
            total += 5 if r.get("kos", 0) > 0 else 3
    return total


def validate_picks(picks):
    """Returns (ok, error). Exactly 3 distinct S1 fighters."""
    if not isinstance(picks, list) or len(picks) != 3:
        return False, "picks must be exactly 3 fighters"
    picks = [str(p).strip().upper() for p in picks]
    if len(set(picks)) != 3:
        return False, "picks must be 3 distinct fighters"
    bad = [p for p in picks if p not in FIGHTERS_S1]
    if bad:
        return False, "unknown fighters: " + ",".join(bad)
    return True, ""
