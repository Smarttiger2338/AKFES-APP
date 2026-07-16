from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from release_public_key import RELEASE_PUBLIC_KEY_B64


def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_release_integrity() -> None:
    if not RELEASE_PUBLIC_KEY_B64:
        return

    executable = Path(sys.executable).resolve()
    manifest = executable.with_suffix(".manifest.json")
    if not manifest.exists():
        raise RuntimeError("AKFES signed release manifest is missing.")

    document = json.loads(manifest.read_text(encoding="utf-8"))
    payload = document["payload"]
    signature = _decode(document["signature"])
    public_key = Ed25519PublicKey.from_public_bytes(_decode(RELEASE_PUBLIC_KEY_B64))
    try:
        public_key.verify(signature, _canonical(payload))
    except InvalidSignature as exc:
        raise RuntimeError("AKFES release signature is invalid.") from exc

    if payload.get("schema") != "akfes-release-v1" or payload.get("product") != "AKFES":
        raise RuntimeError("AKFES release manifest is not valid.")
    if payload.get("filename") != executable.name:
        raise RuntimeError("AKFES executable name does not match its signed manifest.")
    if int(payload.get("size", -1)) != executable.stat().st_size:
        raise RuntimeError("AKFES executable size has changed.")

    digest = hashlib.sha256()
    with executable.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != payload.get("sha256"):
        raise RuntimeError("AKFES executable integrity verification failed.")
