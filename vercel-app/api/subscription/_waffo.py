"""Waffo Pancake integration: signed API calls + webhook verification.

Docs: https://docs.waffo.ai (RSA-SHA256 signing; webhook header x-waffo-signature
with t=<ms>,v1=<base64>; signatureInput = t + "." + raw_body).
Public keys below are Waffo's embedded webhook keys (from @waffo/pancake-ts 0.27.0);
override with WAFFO_WEBHOOK_PUBLIC_KEY env if rotated.
"""
import base64
import hashlib
import json
import os
import time
import urllib.request

API_BASE = "https://api.waffo.ai"

TEST_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAxnmRY6yMMA3lVqmAU6ZG
b1sjL/+r/z6E+ZjkXaDAKiqOhk9rpazni0bNsGXwmftTPk9jy2wn+j6JHODD/WH/
SCnSfvKkLIjy4Hk7BuCgB174C0ydan7J+KgXLkOwgCAxxB68t2tezldwo74ZpXgn
F49opzMvQ9prEwIAWOE+kV9iK6gx/AckSMtHIHpUesoPDkldpmFHlB2qpf1vsFTZ
5kD6DmGl+2GIVK01aChy2lk8pLv0yUMu18v44sLkO5M44TkGPJD9qG09wrvVG2wp
OTVCn1n5pP8P+HRLcgzbUB3OlZVfdFurn6EZwtyL4ZD9kdkQ4EZE/9inKcp3c1h4
xwIDAQAB
-----END PUBLIC KEY-----"""

PROD_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAz+xApdTIb4ua+DgZKQ54
iBsD82ybyhGCLRETONW4Jgbb3A8DUM1LqBk6r/CmTOCHqLalTQHNigvP3R5zkDNX
iRJz6gA4MJ/+8K0+mnEE2RISQzN+Qu65TNd6svb+INm/kMaftY4uIXr6y6kchtTJ
dwnQhcKdAL2v7h7IFnkVelQsKxDdb2PqX8xX/qwd01iXvMcpCCaXovUwZsxH2QN5
ZKBTseJivbhUeyJCco4fdUyxOMHe2ybCVhyvim2uxAl1nkvL5L8RCWMCAV55LLo0
9OhmLahz/DYNu13YLVP6dvIT09ZFBYU6Owj1NxdinTynlJCFS9VYwBgmftosSE1U
dwIDAQAB
-----END PUBLIC KEY-----"""

PRODUCT_ENV = {
    "ringside": "WAFFO_PRODUCT_RINGSIDE",
    "booker": "WAFFO_PRODUCT_BOOKER",
    "promoter": "WAFFO_PRODUCT_PROMOTER",
}


def _priv_key():
    from cryptography.hazmat.primitives import serialization
    pem = os.environ.get("WAFFO_PRIVATE_KEY", "").replace("\\n", "\n")
    if not pem:
        return None
    return serialization.load_pem_private_key(pem.encode(), password=None)


def _pub_key(pem):
    from cryptography.hazmat.primitives import serialization
    return serialization.load_pem_public_key(pem.encode())


def sign_request(method, path, body_str):
    """Returns (timestamp, signature_b64)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    key = _priv_key()
    if key is None:
        raise RuntimeError("WAFFO_PRIVATE_KEY not set")
    ts = str(int(time.time()))
    body_hash = base64.b64encode(hashlib.sha256(body_str.encode()).digest()).decode()
    canonical = "%s\n%s\n%s\n%s" % (method, path, ts, body_hash)
    sig = key.sign(canonical.encode(), padding.PKCS1v15(), hashes.SHA256())
    return ts, base64.b64encode(sig).decode()


def api_post(path, body):
    """Signed POST to Waffo API. Returns parsed JSON."""
    merchant = os.environ.get("WAFFO_MERCHANT_ID", "")
    if not merchant:
        raise RuntimeError("WAFFO_MERCHANT_ID not set")
    body_str = json.dumps(body, separators=(",", ":"))
    ts, sig = sign_request("POST", path, body_str)
    req = urllib.request.Request(
        API_BASE + path, data=body_str.encode(),
        headers={"Content-Type": "application/json",
                 "X-Merchant-Id": merchant,
                 "X-Timestamp": ts,
                 "X-Signature": sig},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def waffo_configured():
    return bool(os.environ.get("WAFFO_MERCHANT_ID") and os.environ.get("WAFFO_PRIVATE_KEY"))


def product_id(tier):
    return os.environ.get(PRODUCT_ENV.get(tier, ""), "")


def create_checkout_session(product_id_, metadata, success_url):
    body = {"productId": product_id_,
            "productType": "subscription",
            "currency": "USD",
            "metadata": metadata,
            "successUrl": success_url}
    res = api_post("/v1/actions/checkout/create-session", body)
    url = res.get("checkoutUrl") or (res.get("data") or {}).get("checkoutUrl", "")
    if not url:
        raise RuntimeError("no checkoutUrl in response: " + json.dumps(res)[:200])
    return url


def _parse_sig_header(header):
    parts = {}
    for kv in (header or "").split(","):
        if "=" in kv:
            k, v = kv.split("=", 1)
            parts[k.strip()] = v.strip()
    return parts.get("t", ""), parts.get("v1", "")


def verify_webhook(payload: bytes, sig_header: str, public_key_pem=None, tolerance_ms=300000):
    """Verifies x-waffo-signature; returns event dict. Raises ValueError."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.exceptions import InvalidSignature
    t, v1 = _parse_sig_header(sig_header)
    if not t or not v1:
        raise ValueError("malformed signature header")
    try:
        ts_ms = int(t)
    except ValueError:
        raise ValueError("bad timestamp in signature header")
    age = int(time.time() * 1000) - ts_ms
    if age > tolerance_ms or age < -60000:
        raise ValueError("webhook timestamp outside tolerance (replay?)")
    if public_key_pem is None:
        public_key_pem = os.environ.get("WAFFO_WEBHOOK_PUBLIC_KEY") or PROD_PUBLIC_KEY
    key = _pub_key(public_key_pem)
    sig_input = (t + ".").encode() + payload
    try:
        key.verify(base64.b64decode(v1), sig_input, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        # try the other env key (test vs prod) like the official SDK
        other = TEST_PUBLIC_KEY if public_key_pem != TEST_PUBLIC_KEY else PROD_PUBLIC_KEY
        key2 = _pub_key(other)
        try:
            key2.verify(base64.b64decode(v1), sig_input, padding.PKCS1v15(), hashes.SHA256())
        except InvalidSignature:
            raise ValueError("invalid webhook signature")
    return json.loads(payload.decode("utf-8"))
