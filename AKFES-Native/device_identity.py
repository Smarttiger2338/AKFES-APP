from __future__ import annotations

import base64
import ctypes
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


_ENTROPY = b"AKFES-DEVICE-IDENTITY-V2"
_APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AKFES"
_KEY_FILE = _APP_DIR / "device_identity.bin"


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes) -> tuple[_DATA_BLOB, object]:
    buffer = ctypes.create_string_buffer(data)
    return _DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def protect_bytes(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("AKFES device protection requires Windows DPAPI.")
    in_blob, in_buffer = _blob(data)
    entropy_blob, entropy_buffer = _blob(_ENTROPY)
    out_blob = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "AKFES device identity",
        ctypes.byref(entropy_blob),
        None,
        None,
        0x1,
        ctypes.byref(out_blob),
    )
    _ = in_buffer, entropy_buffer
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def unprotect_bytes(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("AKFES device protection requires Windows DPAPI.")
    in_blob, in_buffer = _blob(data)
    entropy_blob, entropy_buffer = _blob(_ENTROPY)
    out_blob = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        0x1,
        ctypes.byref(out_blob),
    )
    _ = in_buffer, entropy_buffer
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _hide_file(path: Path) -> None:
    if os.name != "nt":
        return
    try:
        hidden = 0x2
        not_content_indexed = 0x2000
        ctypes.windll.kernel32.SetFileAttributesW(str(path), hidden | not_content_indexed)
    except Exception:
        pass


def _load_or_create_private_key() -> Ed25519PrivateKey:
    _APP_DIR.mkdir(parents=True, exist_ok=True)
    if _KEY_FILE.exists():
        raw = unprotect_bytes(_KEY_FILE.read_bytes())
        if len(raw) != 32:
            raise RuntimeError("Stored AKFES device key is invalid.")
        return Ed25519PrivateKey.from_private_bytes(raw)

    private_key = Ed25519PrivateKey.generate()
    raw = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    protected = protect_bytes(raw)
    temporary = _KEY_FILE.with_suffix(".tmp")
    temporary.write_bytes(protected)
    os.replace(temporary, _KEY_FILE)
    _hide_file(_KEY_FILE)
    return private_key


_PRIVATE_KEY = _load_or_create_private_key()
_PUBLIC_KEY = _PRIVATE_KEY.public_key().public_bytes(
    serialization.Encoding.Raw,
    serialization.PublicFormat.Raw,
)
_DEVICE_ID = hashlib.sha256(_PUBLIC_KEY).hexdigest()


def public_key_b64() -> str:
    return base64.urlsafe_b64encode(_PUBLIC_KEY).rstrip(b"=").decode("ascii")


def device_id() -> str:
    return _DEVICE_ID


def sign_b64(message: bytes) -> str:
    signature = _PRIVATE_KEY.sign(message)
    return base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
