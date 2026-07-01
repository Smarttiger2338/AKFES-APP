from flask import Flask, request, send_file, jsonify, make_response
from flask_cors import CORS
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from io import BytesIO
from functools import wraps
import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse
import uuid

app = Flask(__name__)

MAX_FILE_MB = int(os.environ.get("MAX_FILE_MB", "100"))
MAX_PASSWORD_LENGTH = int(os.environ.get("MAX_PASSWORD_LENGTH", "64"))
MAX_FILENAME_LENGTH = int(os.environ.get("MAX_FILENAME_LENGTH", "120"))
SESSION_EXPIRE_MINUTES = int(os.environ.get("SESSION_EXPIRE_MINUTES", "60"))

LICENSE_SECRET = os.environ.get("LICENSE_SECRET")
SESSION_SECRET = os.environ.get("SESSION_SECRET")

if not LICENSE_SECRET or not SESSION_SECRET:
    raise RuntimeError("LICENSE_SECRET and SESSION_SECRET must be set as environment variables.")

ALLOWED_ORIGINS_RAW = os.environ.get(
    "ALLOWED_ORIGINS",
    "null,http://127.0.0.1:8080,http://localhost:8080"
)
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS_RAW.split(",") if origin.strip()]

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_MB * 1024 * 1024

CORS(
    app,
    origins=ALLOWED_ORIGINS,
    expose_headers=["Content-Disposition"]
)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per hour"],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
)

SALT_SIZE = 16
NONCE_SIZE = 12
KEY_SIZE = 32
PBKDF2_ITERATIONS = 200000

LICENSE_PREFIX = "HCK1"
SESSION_PREFIX = "HCS1"
SESSION_AUDIENCE = "akfes-client"
REVOKED_KEYS_FILE = os.environ.get("REVOKED_KEYS_FILE", "revoked_keys.json")

def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

def b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text + padding).encode("ascii"))

def sign_text(text: str, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).digest()
    return b64url_encode(sig)

def make_signed_token(prefix: str, payload: dict, secret: str) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    body = b64url_encode(payload_json)
    signature = sign_text(f"{prefix}.{body}", secret)
    return f"{prefix}.{body}.{signature}"

def verify_signed_token(token: str, expected_prefix: str, secret: str) -> dict:
    parts = token.split(".")

    if len(parts) != 3:
        raise ValueError("KEY 형식이 올바르지 않습니다.")

    prefix, body, signature = parts

    if prefix != expected_prefix:
        raise ValueError("KEY 종류가 올바르지 않습니다.")

    expected_signature = sign_text(f"{prefix}.{body}", secret)

    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("KEY 서명이 올바르지 않습니다.")

    payload = json.loads(b64url_decode(body).decode("utf-8"))
    now = int(time.time())

    if "nbf" in payload and now < int(payload["nbf"]):
        raise ValueError("아직 사용할 수 없는 KEY입니다.")

    if "exp" in payload and now > int(payload["exp"]):
        raise ValueError("KEY 사용 기간이 만료되었습니다.")

    return payload

def read_revoked_license_ids() -> set:
    try:
        with open(REVOKED_KEYS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("revoked", []))
    except FileNotFoundError:
        return set()
    except Exception:
        app.logger.exception("revoked key list read failed")
        return set()

def is_license_revoked(license_id: str) -> bool:
    if not license_id:
        return False
    return license_id in read_revoked_license_ids()

def create_session_token(license_payload: dict) -> str:
    now = int(time.time())
    license_exp = int(license_payload.get("exp", now))
    exp = min(now + SESSION_EXPIRE_MINUTES * 60, license_exp)

    payload = {
        "sid": str(uuid.uuid4()),
        "iat": now,
        "nbf": now,
        "exp": exp,
        "aud": SESSION_AUDIENCE,
        "license_id": license_payload.get("license_id", ""),
        "license_name": license_payload.get("name", ""),
        "license_exp": license_exp,
        "scope": "file_crypto"
    }

    return make_signed_token(SESSION_PREFIX, payload, SESSION_SECRET)

def require_session(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "로그인이 필요합니다. 라이선스 KEY를 입력하세요."}), 401

        session_token = auth_header.removeprefix("Bearer ").strip()

        try:
            payload = verify_signed_token(session_token, SESSION_PREFIX, SESSION_SECRET)

            if payload.get("scope") != "file_crypto":
                return jsonify({"error": "토큰 권한이 올바르지 않습니다."}), 403

            if payload.get("aud") != SESSION_AUDIENCE:
                return jsonify({"error": "토큰 대상이 올바르지 않습니다."}), 401

            now = int(time.time())

            if now > int(payload.get("license_exp", 0)):
                return jsonify({"error": "라이선스 KEY 사용 기간이 만료되었습니다."}), 401

            if is_license_revoked(payload.get("license_id", "")):
                return jsonify({"error": "폐기된 라이선스 KEY입니다."}), 401

            request.license_id = payload.get("license_id", "")

        except ValueError as e:
            return jsonify({"error": str(e)}), 401
        except Exception:
            app.logger.exception("session token verification failed")
            return jsonify({"error": "인증 토큰 검증에 실패했습니다."}), 401

        return view_func(*args, **kwargs)

    return wrapper

def validate_password(password: str):
    if not password:
        raise ValueError("비밀번호가 비어 있습니다.")

    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"비밀번호는 최대 {MAX_PASSWORD_LENGTH}자까지 허용됩니다.")

    allowed = set("0123456789ABCD*#")

    if any(ch not in allowed for ch in password):
        raise ValueError("비밀번호에는 키패드 문자(0-9, A-D, *, #)만 사용할 수 있습니다.")

def derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=KEY_SIZE
    )

def clean_original_filename(raw_name: str) -> str:
    name = (raw_name or "").replace("\\", "/").split("/")[-1].strip()
    name = name.replace("\x00", "")
    return name or "uploaded_file"

def remove_trailing_crypto_tag(stem: str) -> str:
    for tag in ("[암호화됨]", "[복호화됨]"):
        if stem.endswith(tag):
            return stem[:-len(tag)]
    return stem

def add_tag_before_extension(filename: str, tag: str) -> str:
    name, ext = os.path.splitext(filename)
    name = remove_trailing_crypto_tag(name)
    return f"{name}{tag}{ext}"

def encrypt_bytes(data: bytes, password: str) -> bytes:
    salt = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)
    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return salt + nonce + ciphertext

def decrypt_bytes(data: bytes, password: str) -> bytes:
    min_size = SALT_SIZE + NONCE_SIZE + 16

    if len(data) < min_size:
        raise ValueError("암호화된 파일 형식이 올바르지 않습니다.")

    salt = data[:SALT_SIZE]
    nonce = data[SALT_SIZE:SALT_SIZE + NONCE_SIZE]
    ciphertext = data[SALT_SIZE + NONCE_SIZE:]

    key = derive_key(password, salt)
    aesgcm = AESGCM(key)

    try:
        return aesgcm.decrypt(nonce, ciphertext, None)
    except Exception:
        raise ValueError("비밀번호가 틀렸거나 파일이 손상되었습니다.")

@app.errorhandler(413)
def file_too_large(_):
    return jsonify({"error": f"파일이 너무 큽니다. 현재 제한은 {MAX_FILE_MB}MB입니다."}), 413

@app.errorhandler(429)
def rate_limit_exceeded(_):
    return jsonify({"error": "요청이 너무 많습니다. 잠시 후 다시 시도하세요."}), 429

@app.after_request
def add_security_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response

@app.route("/health", methods=["GET"])
@limiter.limit("30 per minute")
def health():
    return jsonify({
        "ok": True,
        "project": "AKFES",
        "mode": "public-server-with-license-key",
        "max_file_mb": MAX_FILE_MB,
        "max_password_length": MAX_PASSWORD_LENGTH,
        "max_filename_length": MAX_FILENAME_LENGTH,
        "session_expire_minutes": SESSION_EXPIRE_MINUTES,
        "ciphertext_format": "opaque-binary"
    })

@app.route("/auth/login", methods=["POST"])
@limiter.limit("5 per minute")
def login_with_license_key():
    body = request.get_json(silent=True) or {}
    license_key = str(body.get("license_key", "")).strip()

    if not license_key:
        return jsonify({"error": "라이선스 KEY를 입력하세요."}), 400

    try:
        license_payload = verify_signed_token(license_key, LICENSE_PREFIX, LICENSE_SECRET)
        license_id = license_payload.get("license_id", "")

        if is_license_revoked(license_id):
            app.logger.warning("login rejected revoked license_id=%s ip=%s", license_id, request.remote_addr)
            return jsonify({"error": "폐기된 라이선스 KEY입니다."}), 401

        session_token = create_session_token(license_payload)

        app.logger.info("login success license_id=%s ip=%s", license_id, request.remote_addr)

        return jsonify({
            "ok": True,
            "session_token": session_token,
            "license_id": license_id,
            "license_name": license_payload.get("name", ""),
            "license_expires_at": license_payload.get("exp", 0),
            "session_expires_in_minutes": SESSION_EXPIRE_MINUTES
        })

    except ValueError as e:
        app.logger.warning("login failed ip=%s reason=%s", request.remote_addr, str(e))
        return jsonify({"error": str(e)}), 401
    except Exception:
        app.logger.exception("unexpected login error")
        return jsonify({"error": "라이선스 KEY 검증에 실패했습니다."}), 401

@app.route("/process", methods=["POST"])
@limiter.limit("10 per minute")
@require_session
def process():
    mode = request.form.get("mode", "")
    password = request.form.get("password", "")

    if mode not in ("encrypt", "decrypt"):
        return jsonify({"error": "작업 모드가 올바르지 않습니다."}), 400

    try:
        validate_password(password)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if "file" not in request.files:
        return jsonify({"error": "파일이 없습니다."}), 400

    uploaded = request.files["file"]

    if not uploaded.filename:
        return jsonify({"error": "파일명이 비어 있습니다."}), 400

    original_filename = clean_original_filename(uploaded.filename)

    if len(original_filename) > MAX_FILENAME_LENGTH:
        return jsonify({"error": f"파일명은 최대 {MAX_FILENAME_LENGTH}자까지 허용됩니다."}), 400

    try:
        input_data = uploaded.read()

        if not input_data:
            return jsonify({"error": "빈 파일은 처리할 수 없습니다."}), 400

        if mode == "encrypt":
            output_data = encrypt_bytes(input_data, password)
            download_name = add_tag_before_extension(original_filename, "[암호화됨]")
        else:
            output_data = decrypt_bytes(input_data, password)
            download_name = add_tag_before_extension(original_filename, "[복호화됨]")

        quoted = urllib.parse.quote(download_name)

        response = make_response(send_file(
            BytesIO(output_data),
            as_attachment=True,
            download_name=download_name,
            mimetype="application/octet-stream"
        ))

        response.headers["Content-Disposition"] = (
            f"attachment; filename*=UTF-8''{quoted}"
        )

        app.logger.info(
            "process success license_id=%s mode=%s filename_len=%s ip=%s",
            getattr(request, "license_id", ""),
            mode,
            len(original_filename),
            request.remote_addr
        )

        return response

    except ValueError as e:
        app.logger.warning(
            "process failed license_id=%s mode=%s ip=%s reason=%s",
            getattr(request, "license_id", ""),
            mode,
            request.remote_addr,
            str(e)
        )
        return jsonify({"error": str(e)}), 400
    except Exception:
        app.logger.exception("unexpected process error")
        return jsonify({"error": "서버 처리 중 오류가 발생했습니다."}), 500

if __name__ == "__main__":
    host = os.environ.get("SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("SERVER_PORT", "5000"))
    debug = False
    app.run(host=host, port=port, debug=debug)
