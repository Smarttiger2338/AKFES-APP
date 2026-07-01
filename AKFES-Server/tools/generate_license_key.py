import base64
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from datetime import datetime

LICENSE_PREFIX = "HCK1"
LICENSE_SECRET = os.environ.get("LICENSE_SECRET")

if not LICENSE_SECRET:
    raise RuntimeError("LICENSE_SECRET must be set as an environment variable.")

def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

def sign_text(text: str, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).digest()
    return b64url_encode(sig)

def parse_lifetime(value: str) -> int:
    value = value.strip().lower()
    if len(value) < 2:
        raise ValueError("기간 형식 예: 3h, 1d, 2w, 3m, 1y")
    number = int(value[:-1])
    unit = value[-1]
    table = {
        "h": 60 * 60,
        "d": 24 * 60 * 60,
        "w": 7 * 24 * 60 * 60,
        "m": 30 * 24 * 60 * 60,
        "y": 365 * 24 * 60 * 60,
    }
    if unit not in table:
        raise ValueError("지원 단위: h, d, w, m, y")
    return number * table[unit]

def make_license_key(payload: dict) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    body = b64url_encode(payload_json)
    signature = sign_text(f"{LICENSE_PREFIX}.{body}", LICENSE_SECRET)
    return f"{LICENSE_PREFIX}.{body}.{signature}"

def main():
    if len(sys.argv) < 2:
        print("사용법: python generate_license_key.py <기간> [사용자이름]")
        print("예: python generate_license_key.py 1d user1")
        print("기간 단위: h=시간, d=일, w=주, m=개월(30일), y=년(365일)")
        sys.exit(1)
    lifetime = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) >= 3 else "user"
    now = int(time.time())
    exp = now + parse_lifetime(lifetime)
    payload = {
        "license_id": str(uuid.uuid4()),
        "name": name,
        "iat": now,
        "nbf": now,
        "exp": exp,
        "lifetime": lifetime,
        "scope": "file_crypto"
    }
    key = make_license_key(payload)
    print("=== LICENSE KEY ===")
    print(key)
    print()
    print("사용자:", name)
    print("기간:", lifetime)
    print("만료:", datetime.fromtimestamp(exp).strftime("%Y-%m-%d %H:%M:%S"))

if __name__ == "__main__":
    main()
