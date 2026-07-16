from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from flask import jsonify, make_response, request

import server as core


PROTOCOL = "AKFES-OP-V2"
CHALLENGE_TTL_SECONDS = int(os.environ.get("CHALLENGE_TTL_SECONDS", "30"))
MAX_CLOCK_SKEW_SECONDS = int(os.environ.get("MAX_CLOCK_SKEW_SECONDS", "30"))
DEVICE_SESSIONS: dict[str, dict] = {}
CHALLENGES: dict[str, dict] = {}
STATE_LOCK = threading.RLock()


class AttestationError(ValueError):
    pass


def _decode(text: str) -> bytes:
    return core.b64url_decode(text)


def _validate_device(public_key_text: str, device_id: str) -> tuple[str, str]:
    try:
        raw = _decode(public_key_text)
    except Exception as exc:
        raise AttestationError("장치 공개키 형식이 올바르지 않습니다.") from exc
    if len(raw) != 32:
        raise AttestationError("장치 공개키 길이가 올바르지 않습니다.")
    expected_id = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(expected_id, device_id):
        raise AttestationError("장치 식별 정보가 일치하지 않습니다.")
    Ed25519PublicKey.from_public_bytes(raw)
    return core.b64url_encode(raw), expected_id


def _validate_session() -> dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise AttestationError("인증 세션이 필요합니다.")
    token = auth_header.removeprefix("Bearer ").strip()
    payload = core.verify_signed_token(token, core.SESSION_PREFIX, core.SESSION_SECRET)
    if payload.get("scope") != "file_crypto" or payload.get("aud") != core.SESSION_AUDIENCE:
        raise AttestationError("세션 권한이 올바르지 않습니다.")
    if int(time.time()) > int(payload.get("license_exp", 0)):
        raise AttestationError("라이선스 사용 기간이 만료되었습니다.")
    if core.is_license_revoked(payload.get("license_id", "")):
        raise AttestationError("폐기된 라이선스입니다.")

    sid = str(payload.get("sid", ""))
    with STATE_LOCK:
        device = DEVICE_SESSIONS.get(sid)
    if not device:
        raise AttestationError("장치 인증 세션이 없습니다. 다시 로그인하세요.")
    if int(device.get("expires_at", 0)) < int(time.time()):
        raise AttestationError("장치 인증 세션이 만료되었습니다.")
    header_device_id = request.headers.get("X-AKFES-Device-ID", "")
    if not hmac.compare_digest(header_device_id, device["device_id"]):
        raise AttestationError("요청 장치가 로그인 장치와 다릅니다.")
    payload["_device"] = device
    return payload


def _cleanup_state(now: int) -> None:
    expired_sessions = [sid for sid, item in DEVICE_SESSIONS.items() if int(item.get("expires_at", 0)) < now]
    for sid in expired_sessions:
        DEVICE_SESSIONS.pop(sid, None)
        CHALLENGES.pop(sid, None)
    expired_challenges = [sid for sid, item in CHALLENGES.items() if int(item.get("expires_at", 0)) < now]
    for sid in expired_challenges:
        CHALLENGES.pop(sid, None)


def _canonical_message(
    challenge: str,
    timestamp: int,
    device_id: str,
    mode: str,
    filename: str,
    file_size: int,
    file_sha256: str,
    password: str,
) -> bytes:
    password_sha256 = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return "\n".join(
        [
            PROTOCOL,
            challenge,
            str(timestamp),
            device_id,
            mode,
            filename,
            str(file_size),
            file_sha256,
            password_sha256,
        ]
    ).encode("utf-8")


def _verify_process_attestation() -> None:
    payload = _validate_session()
    sid = str(payload["sid"])
    device = payload["_device"]

    if request.headers.get("X-AKFES-Protocol", "") != PROTOCOL:
        raise AttestationError("지원하지 않는 보안 프로토콜입니다.")

    try:
        timestamp = int(request.headers.get("X-AKFES-Timestamp", "0"))
    except ValueError as exc:
        raise AttestationError("요청 시각이 올바르지 않습니다.") from exc
    now = int(time.time())
    if abs(now - timestamp) > MAX_CLOCK_SKEW_SECONDS:
        raise AttestationError("요청 유효 시간이 지났습니다.")

    challenge = request.headers.get("X-AKFES-Challenge", "")
    with STATE_LOCK:
        _cleanup_state(now)
        issued = CHALLENGES.get(sid)
    if not issued or not hmac.compare_digest(str(issued.get("challenge", "")), challenge):
        raise AttestationError("일회용 보안 챌린지가 올바르지 않습니다.")
    if int(issued.get("expires_at", 0)) < now:
        raise AttestationError("일회용 보안 챌린지가 만료되었습니다.")

    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        raise AttestationError("서명할 파일이 없습니다.")
    raw_data = uploaded.stream.read()
    uploaded.stream.seek(0)
    actual_size = len(raw_data)
    actual_hash = hashlib.sha256(raw_data).hexdigest()

    header_size = request.headers.get("X-AKFES-File-Size", "")
    header_hash = request.headers.get("X-AKFES-File-SHA256", "")
    if header_size != str(actual_size) or not hmac.compare_digest(header_hash, actual_hash):
        raise AttestationError("업로드 파일 무결성 검증에 실패했습니다.")

    mode = str(request.form.get("mode", ""))
    password = str(request.form.get("password", ""))
    filename = core.clean_original_filename(uploaded.filename)
    message = _canonical_message(
        challenge,
        timestamp,
        device["device_id"],
        mode,
        filename,
        actual_size,
        actual_hash,
        password,
    )

    try:
        signature = _decode(request.headers.get("X-AKFES-Signature", ""))
        public_key = Ed25519PublicKey.from_public_bytes(_decode(device["public_key"]))
        public_key.verify(signature, message)
    except (ValueError, InvalidSignature) as exc:
        raise AttestationError("요청 전자서명 검증에 실패했습니다.") from exc

    with STATE_LOCK:
        current = CHALLENGES.get(sid)
        if not current or not hmac.compare_digest(str(current.get("challenge", "")), challenge):
            raise AttestationError("이미 사용된 보안 챌린지입니다.")
        CHALLENGES.pop(sid, None)


_original_login = core.app.view_functions["login_with_license_key"]


def hardened_login():
    body = request.get_json(silent=True) or {}
    try:
        public_key, device_id = _validate_device(
            str(body.get("device_public_key", "")).strip(),
            str(body.get("device_id", "")).strip(),
        )
    except AttestationError as exc:
        return jsonify({"error": str(exc)}), 401

    response = make_response(_original_login())
    if response.status_code >= 400:
        return response
    data = response.get_json(silent=True) or {}
    token = str(data.get("session_token", ""))
    try:
        session_payload = core.verify_signed_token(token, core.SESSION_PREFIX, core.SESSION_SECRET)
    except Exception:
        return jsonify({"error": "세션 발급 검증에 실패했습니다."}), 500

    sid = str(session_payload.get("sid", ""))
    with STATE_LOCK:
        _cleanup_state(int(time.time()))
        DEVICE_SESSIONS[sid] = {
            "public_key": public_key,
            "device_id": device_id,
            "expires_at": int(session_payload.get("exp", 0)),
            "client_version": str(body.get("client_version", ""))[:32],
        }
    data["device_id"] = device_id
    data["attestation_required"] = True
    return jsonify(data), response.status_code


core.app.view_functions["login_with_license_key"] = hardened_login


@core.app.route("/auth/challenge", methods=["POST"])
@core.limiter.limit("30 per minute")
def issue_challenge():
    try:
        payload = _validate_session()
        sid = str(payload["sid"])
        now = int(time.time())
        challenge = core.b64url_encode(os.urandom(32))
        with STATE_LOCK:
            _cleanup_state(now)
            CHALLENGES[sid] = {
                "challenge": challenge,
                "expires_at": now + CHALLENGE_TTL_SECONDS,
            }
        return jsonify({
            "ok": True,
            "challenge": challenge,
            "expires_in": CHALLENGE_TTL_SECONDS,
            "protocol": PROTOCOL,
        })
    except (ValueError, AttestationError) as exc:
        return jsonify({"error": str(exc)}), 401
    except Exception:
        core.app.logger.exception("challenge issue failed")
        return jsonify({"error": "보안 챌린지 발급에 실패했습니다."}), 500


@core.app.before_request
def enforce_attested_process_request():
    if request.path != "/process" or request.method != "POST":
        return None
    try:
        _verify_process_attestation()
    except (ValueError, AttestationError) as exc:
        core.app.logger.warning("device attestation failed ip=%s reason=%s", request.remote_addr, str(exc))
        return jsonify({"error": str(exc)}), 401
    except Exception:
        core.app.logger.exception("unexpected device attestation failure")
        return jsonify({"error": "장치 인증 검증에 실패했습니다."}), 401
    return None


if __name__ == "__main__":
    host = os.environ.get("SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("SERVER_PORT", "5000"))
    core.app.run(host=host, port=port, debug=False)
