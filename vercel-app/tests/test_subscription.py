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

# ---- 7. waffo sign / verify roundtrip ----
sys.path.insert(0, os.path.expanduser("~/workspace/brawlverse/vercel-app/api/subscription"))
import _waffo as W

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_priv_pem = _key.private_bytes(serialization.Encoding.PEM,
                              serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()).decode()
_pub_pem = _key.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo).decode()

os.environ["WAFFO_PRIVATE_KEY"] = _priv_pem
os.environ["WAFFO_MERCHANT_ID"] = "MER_test"
ts, sig = W.sign_request("POST", "/v1/actions/checkout/create-session", '{"a":1}')
check("sign_request returns ts+sig", bool(ts) and bool(sig))

import base64 as _b64, hashlib as _hl, json as _js, time as _t
# verify canonical construction manually
body = '{"a":1}'
bh = _b64.b64encode(_hl.sha256(body.encode()).digest()).decode()
canon = "POST\n/v1/actions/checkout/create-session\n%s\n%s" % (ts, bh)
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
try:
    _key.public_key().verify(_b64.b64decode(sig), canon.encode(),
                             padding.PKCS1v15(), hashes.SHA256())
    check("signature verifies against canonical", True)
except Exception:
    check("signature verifies against canonical", False)

# webhook verify roundtrip with our own keypair
payload = _js.dumps({"id": "evt_1", "eventType": "subscription.activated",
                     "mode": "test", "data": {"metadata": {"device_hash": "dh", "tier": "booker"}}}).encode()
t_ms = str(int(_t.time() * 1000))
sig_input = (t_ms + ".").encode() + payload
vsig = _b64.b64encode(_key.sign(sig_input, padding.PKCS1v15(), hashes.SHA256())).decode()
ev = W.verify_webhook(payload, "t=%s,v1=%s" % (t_ms, vsig), public_key_pem=_pub_pem)
check("webhook roundtrip", ev["eventType"] == "subscription.activated")

# tampered body fails
try:
    W.verify_webhook(payload + b"x", "t=%s,v1=%s" % (t_ms, vsig), public_key_pem=_pub_pem)
    check("tamper rejected", False)
except ValueError:
    check("tamper rejected", True)

# stale timestamp fails
old_t = str(int(_t.time() * 1000) - 600000)
old_in = (old_t + ".").encode() + payload
old_sig = _b64.b64encode(_key.sign(old_in, padding.PKCS1v15(), hashes.SHA256())).decode()
try:
    W.verify_webhook(payload, "t=%s,v1=%s" % (old_t, old_sig), public_key_pem=_pub_pem)
    check("stale rejected", False)
except ValueError:
    check("stale rejected", True)

# malformed header fails
try:
    W.verify_webhook(payload, "garbage", public_key_pem=_pub_pem)
    check("malformed rejected", False)
except ValueError:
    check("malformed rejected", True)

check("waffo_configured true with env", W.waffo_configured())
del os.environ["WAFFO_PRIVATE_KEY"]
check("waffo_configured false without key", not W.waffo_configured())
os.environ.pop("WAFFO_MERCHANT_ID", None)

print("---\n%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
