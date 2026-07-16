from __future__ import annotations

import hmac
import os
from typing import Any

from flask import Flask, jsonify, request


_ALLOWED_ROUTES: dict[str, set[str]] = {
    "/health": {"GET"},
    "/auth/login": {"POST"},
    "/auth/challenge": {"POST"},
    "/process": {"POST"},
}

_LOGIN_FIELDS = {"license_key", "device_public_key", "device_id", "client_version"}
_PROCESS_FORM_FIELDS = {"mode", "password"}
_PROCESS_FILE_FIELDS = {"file"}


def _error(message: str, status: int):
    return jsonify({"error": message}), status


def _require_str_field(body: dict[str, Any], name: str, max_length: int) -> str:
    value = body.get(name)
    if not isinstance(value, str):
        raise ValueError(f"{name} 형식이 올바르지 않습니다.")
    value = value.strip()
    if not value or len(value) > max_length:
        raise ValueError(f"{name} 길이가 올바르지 않습니다.")
    return value


def install_server_boundary(app: Flask, core) -> None:
    license_secret = str(core.LICENSE_SECRET)
    session_secret = str(core.SESSION_SECRET)
    if len(license_secret) < 32 or len(session_secret) < 32:
        raise RuntimeError("LICENSE_SECRET and SESSION_SECRET must each be at least 32 characters.")
    if hmac.compare_digest(license_secret, session_secret):
        raise RuntimeError("LICENSE_SECRET and SESSION_SECRET must be different.")

    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.config["TRAP_HTTP_EXCEPTIONS"] = False
    app.config["MAX_FORM_PARTS"] = 4
    app.config["MAX_FORM_MEMORY_SIZE"] = 128 * 1024

    trusted_hosts = [item.strip() for item in os.environ.get("TRUSTED_HOSTS", "").split(",") if item.strip()]
    if trusted_hosts:
        app.config["TRUSTED_HOSTS"] = trusted_hosts

    @app.before_request
    def enforce_closed_api_surface():
        path = request.path.rstrip("/") or "/"
        methods = _ALLOWED_ROUTES.get(path)
        if methods is None:
            return _error("존재하지 않는 API 경로입니다.", 404)
        if request.method not in methods:
            return _error("허용되지 않은 요청 방식입니다.", 405)
        if request.headers.get("X-HTTP-Method-Override") or request.headers.get("X-Method-Override"):
            return _error("요청 방식 재정의는 허용되지 않습니다.", 400)
        if request.query_string:
            return _error("쿼리 문자열은 허용되지 않습니다.", 400)

        content_length = request.content_length or 0

        if path == "/health":
            if content_length:
                return _error("상태 확인 요청에는 본문을 보낼 수 없습니다.", 400)
            return None

        if path == "/auth/login":
            if not request.is_json:
                return _error("로그인 요청은 JSON 형식이어야 합니다.", 415)
            if content_length > 16 * 1024:
                return _error("로그인 요청이 너무 큽니다.", 413)
            body = request.get_json(silent=True)
            if not isinstance(body, dict):
                return _error("로그인 요청 본문이 올바르지 않습니다.", 400)
            unknown = set(body) - _LOGIN_FIELDS
            if unknown:
                return _error("허용되지 않은 로그인 필드가 포함되어 있습니다.", 400)
            try:
                _require_str_field(body, "license_key", 8192)
                _require_str_field(body, "device_public_key", 256)
                _require_str_field(body, "device_id", 128)
                _require_str_field(body, "client_version", 32)
            except ValueError as exc:
                return _error(str(exc), 400)
            return None

        if path == "/auth/challenge":
            if content_length:
                return _error("챌린지 요청에는 본문을 보낼 수 없습니다.", 400)
            return None

        if path == "/process":
            content_type = (request.content_type or "").lower()
            if not content_type.startswith("multipart/form-data"):
                return _error("파일 처리 요청은 multipart/form-data 형식이어야 합니다.", 415)

            maximum = core.MAX_FILE_MB * 1024 * 1024 + 256 * 1024
            if content_length > maximum:
                return _error("파일 처리 요청이 허용 크기를 초과했습니다.", 413)

            if set(request.form) != _PROCESS_FORM_FIELDS:
                return _error("파일 처리 필드 구성이 올바르지 않습니다.", 400)
            if set(request.files) != _PROCESS_FILE_FIELDS:
                return _error("파일 업로드 필드 구성이 올바르지 않습니다.", 400)
            if len(request.files.getlist("file")) != 1:
                return _error("한 번에 하나의 파일만 처리할 수 있습니다.", 400)
            return None

        return _error("요청을 처리할 수 없습니다.", 400)

    @app.after_request
    def lock_api_response(response):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        response.headers["X-AKFES-API"] = "closed-surface-v1"
        return response
