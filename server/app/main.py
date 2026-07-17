from __future__ import annotations

import secrets

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from .auth import router as auth_router
from .config import Settings, get_settings
from .health import HealthResponse, health, router as health_router
from .license_service import LicenseService
from .license_store import LicenseStore
from .request_security import RequestSecurityService
from .signed_requests import router as signed_requests_router


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    docs_url = "/docs" if resolved_settings.docs_enabled else None
    openapi_url = "/openapi.json" if resolved_settings.docs_enabled else None

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.version,
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=openapi_url,
    )
    app.state.settings = resolved_settings
    license_service = LicenseService(
        store=LicenseStore(resolved_settings.database_path),
        hmac_secret=resolved_settings.license_hmac_secret,
        session_ttl_seconds=resolved_settings.session_ttl_seconds,
    )
    app.state.license_service = license_service
    app.state.request_security = RequestSecurityService(
        license_service=license_service,
        challenge_ttl_seconds=resolved_settings.challenge_ttl_seconds,
    )
    app.dependency_overrides[get_settings] = lambda: resolved_settings

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(resolved_settings.allowed_hosts),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-AKFES-Admin-Token",
            "X-AKFES-Admin-Actor",
            "X-AKFES-Device-ID",
            "X-AKFES-Challenge",
            "X-AKFES-Signature",
        ],
        expose_headers=["Content-Disposition", "X-Request-ID"],
        max_age=600,
    )

    @app.middleware("http")
    async def add_security_headers(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Request-ID"] = secrets.token_urlsafe(16)
        return response

    app.include_router(health_router, prefix="/api/v2")
    app.include_router(auth_router, prefix="/api/v2")
    app.include_router(signed_requests_router, prefix="/api/v2")
    app.add_api_route(
        "/health",
        health,
        methods=["GET"],
        response_model=HealthResponse,
        include_in_schema=False,
    )
    return app


app = create_app()
