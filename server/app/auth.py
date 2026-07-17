from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from .license_service import (
    ExpiredLicenseError,
    InvalidLicenseError,
    InvalidSessionError,
    LicenseService,
    RevokedLicenseError,
)

router = APIRouter()


class IssueLicenseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_seconds: int = Field(ge=60, le=315_360_000)
    label: str | None = Field(default=None, max_length=120)


class IssueLicenseResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    license_key: str
    license_id: int
    created_at: int
    expires_at: int


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    license_key: str = Field(min_length=1, max_length=128)
    device_id: str | None = Field(default=None, max_length=128)


class LoginResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_token: str
    license_id: int
    license_expires_at: int
    session_expires_at: int
    device_id: str | None


class SessionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    valid: bool
    license_id: int
    session_expires_at: int
    device_id: str | None


def get_license_service(request: Request) -> LicenseService:
    return request.app.state.license_service


def require_admin_token(request: Request, token: str | None) -> None:
    expected = request.app.state.settings.admin_token
    if token is None or not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrator token",
        )


def bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
        )
    return token.strip()


@router.post(
    "/admin/licenses",
    response_model=IssueLicenseResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["admin"],
)
def issue_license(
    payload: IssueLicenseRequest,
    request: Request,
    x_akfes_admin_token: Annotated[str | None, Header()] = None,
) -> IssueLicenseResponse:
    require_admin_token(request, x_akfes_admin_token)
    issued = get_license_service(request).issue_license(
        duration_seconds=payload.duration_seconds,
        label=payload.label,
    )
    return IssueLicenseResponse(
        license_key=issued.license_key,
        license_id=issued.license_id,
        created_at=issued.created_at,
        expires_at=issued.expires_at,
    )


@router.post("/auth/login", response_model=LoginResponse, tags=["authentication"])
def login(payload: LoginRequest, request: Request) -> LoginResponse:
    try:
        session = get_license_service(request).authenticate(
            license_key=payload.license_key,
            device_id=payload.device_id,
        )
    except InvalidLicenseError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid license key",
        ) from error
    except ExpiredLicenseError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="License has expired",
        ) from error
    except RevokedLicenseError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="License has been revoked",
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    return LoginResponse(
        session_token=session.session_token,
        license_id=session.license_id,
        license_expires_at=session.license_expires_at,
        session_expires_at=session.session_expires_at,
        device_id=session.device_id,
    )


@router.get("/auth/session", response_model=SessionResponse, tags=["authentication"])
def session_status(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_akfes_device_id: Annotated[str | None, Header()] = None,
) -> SessionResponse:
    token = bearer_token(authorization)
    try:
        session = get_license_service(request).verify_session(
            token,
            device_id=x_akfes_device_id,
        )
    except (InvalidSessionError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from error

    return SessionResponse(
        valid=True,
        license_id=session.license_id,
        session_expires_at=session.expires_at,
        device_id=session.device_id,
    )
