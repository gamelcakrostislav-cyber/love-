#!/usr/bin/env python3
"""Reference client for the control plane.

Does the full happy path with no third-party deps:
  1. POST /auth/session   — exchange API key + device fingerprint for a token
  2. GET  /v1/opportunities — call the engine with the token, HMAC-signing the
     request (timestamp + nonce + signature) exactly as the gateway expects.

Usage:
  python scripts/client_example.py \
      --base-url http://localhost:8000 \
      --api-key <YOUR_KEY> \
      --fingerprint my-laptop-001
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.request


def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _sign(secret: str, ts: str, nonce: str, method: str, path: str, body: bytes) -> str:
    body_digest = hashlib.sha256(body).hexdigest()
    msg = "\n".join([ts, nonce, method.upper(), path, body_digest])
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--fingerprint", default="my-laptop-001")
    ap.add_argument("--path", default="/v1/opportunities")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")

    # 1. Session exchange (the raw key is used here and nowhere else).
    session = _post_json(
        f"{base}/auth/session",
        {"api_key": args.api_key, "device_fingerprint": args.fingerprint},
    )
    token = session["token"]
    signing_secret = session["signing_secret"]
    print(f"✓ session: plan={session['plan']} expires={session['expires_at']}")
    if session.get("flagged"):
        print("  ⚠️  this key is flagged for review")

    # 2. Signed call to the protected engine.
    ts = str(int(time.time()))
    nonce = secrets.token_hex(16)
    signature = _sign(signing_secret, ts, nonce, "GET", args.path, b"")
    req = urllib.request.Request(
        f"{base}{args.path}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Device-Fingerprint": args.fingerprint,
            "X-Timestamp": ts,
            "X-Nonce": nonce,
            "X-Signature": signature,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        print(f"✗ engine call failed: {exc.code} {exc.read().decode()}")
        return

    print(f"✓ opportunities ({result['count']}, plan={result['plan']}):")
    for op in result["items"]:
        print(f"    {op['id']}  {op['pair']:10s}  {op['profitability'] * 100:.1f}%  "
              f"{op['market']}")


if __name__ == "__main__":
    main()
