from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def load_or_create_private(path: Path) -> Ed25519PrivateKey:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), password=None)
    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(pem)
    os.replace(temporary, path)
    return private


def write_public_module(private: Ed25519PrivateKey, destination: Path) -> None:
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    destination.write_text(f'RELEASE_PUBLIC_KEY_B64 = "{b64(public_raw)}"\n', encoding="utf-8")


def canonical_payload(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_release(private: Ed25519PrivateKey, executable: Path, manifest: Path) -> None:
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    payload = {
        "schema": "akfes-release-v1",
        "product": "AKFES",
        "version": "2.0.0",
        "build_id": secrets.token_hex(16),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "filename": executable.name,
        "size": executable.stat().st_size,
        "sha256": digest,
    }
    signature = private.sign(canonical_payload(payload))
    manifest.write_text(
        json.dumps({"payload": payload, "signature": b64(signature)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare")
    prepare.add_argument("--private", required=True)
    prepare.add_argument("--public-module", required=True)

    sign = sub.add_parser("sign")
    sign.add_argument("--private", required=True)
    sign.add_argument("--exe", required=True)
    sign.add_argument("--manifest", required=True)

    args = parser.parse_args()
    private = load_or_create_private(Path(args.private))
    if args.command == "prepare":
        write_public_module(private, Path(args.public_module))
    else:
        sign_release(private, Path(args.exe), Path(args.manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
