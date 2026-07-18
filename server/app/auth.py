from __future__ import annotations

import hmac
import time
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from .license_service import (
    DeviceBindingError,
    ExpiredLicenseError,
    InvalidLicenseError,
    InvalidSessionError,
    LicenseNotFoundError,
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


class LicenseSummaryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    license_id: int
    label: str | None
    created_at: int
    expires_at: int
    revoked_at: int | None
    status: str
    device_bound: bool
    active_session_count: int


class AdminReasonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=240)


class RevokeLicenseResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    license_id: int
    revoked_at: int


class ResetDeviceBindingResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    license_id: int
    reset_at: int


class AuditResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    audit_id: int
    action: str
    actor: str
    target_type: str
    target_id: str | None
    details: dict[str, object]
    created_at: int


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


def license_status(expires_at: int, revoked_at: int | None, now: int) -> str:
    if revoked_at is not None:
        return "revoked"
    if expires_at <= now:
        return "expired"
    return "active"


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
    x_akfes_admin_actor: Annotated[str | None, Header()] = None,
) -> IssueLicenseResponse:
    require_admin_token(request, x_akfes_admin_token)
    issued = get_license_service(request).issue_license(
        duration_seconds=payload.duration_seconds,
        label=payload.label,
        actor=x_akfes_admin_actor,
    )
    return IssueLicenseResponse(
        license_key=issued.license_key,
        license_id=issued.license_id,
        created_at=issued.created_at,
        expires_at=issued.expires_at,
    )


@router.get(
    "/admin/licenses",
    response_model=list[LicenseSummaryResponse],
    tags=["admin"],
)
def list_licenses(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    x_akfes_admin_token: Annotated[str | None, Header()] = None,
) -> list[LicenseSummaryResponse]:
    require_admin_token(request, x_akfes_admin_token)
    now = int(time.time())
    records = get_license_service(request).list_licenses(limit=limit, offset=offset, now=now)
    return [
        LicenseSummaryResponse(
            license_id=record.license_id,
            label=record.label,
            created_at=record.created_at,
            expires_at=record.expires_at,
            revoked_at=record.revoked_at,
            status=license_status(record.expires_at, record.revoked_at, now),
            device_bound=record.device_bound,
            active_session_count=record.active_session_count,
        )
        for record in records
    ]


@router.post(
    "/admin/licenses/{license_id}/revoke",
    response_model=RevokeLicenseResponse,
    tags=["admin"],
)
def revoke_license(
    license_id: int,
    payload: AdminReasonRequest,
    request: Request,
    x_akfes_admin_token: Annotated[str | None, Header()] = None,
    x_akfes_admin_actor: Annotated[str | None, Header()] = None,
) -> RevokeLicenseResponse:
    require_admin_token(request, x_akfes_admin_token)
    try:
        revoked_at = get_license_service(request).revoke_license(
            license_id=license_id,
            actor=x_akfes_admin_actor,
            reason=payload.reason,
        )
    except LicenseNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License does not exist or is already revoked",
        ) from error
    return RevokeLicenseResponse(license_id=license_id, revoked_at=revoked_at)


@router.post(
    "/admin/licenses/{license_id}/device-binding/reset",
    response_model=ResetDeviceBindingResponse,
    tags=["admin"],
)
def reset_device_binding(
    license_id: int,
    payload: AdminReasonRequest,
    request: Request,
    x_akfes_admin_token: Annotated[str | None, Header()] = None,
    x_akfes_admin_actor: Annotated[str | None, Header()] = None,
) -> ResetDeviceBindingResponse:
    require_admin_token(request, x_akfes_admin_token)
    try:
        reset_at = get_license_service(request).reset_device_binding(
            license_id=license_id,
            actor=x_akfes_admin_actor,
            reason=payload.reason,
        )
    except LicenseNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License is missing, revoked, or not device-bound",
        ) from error
    return ResetDeviceBindingResponse(license_id=license_id, reset_at=reset_at)


@router.get(
    "/admin/audit",
    response_model=list[AuditResponse],
    tags=["admin"],
)
def list_audit(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    x_akfes_admin_token: Annotated[str | None, Header()] = None,
) -> list[AuditResponse]:
    require_admin_token(request, x_akfes_admin_token)
    records = get_license_service(request).list_audit(limit=limit, offset=offset)
    return [
        AuditResponse(
            audit_id=record.audit_id,
            action=record.action,
            actor=record.actor,
            target_type=record.target_type,
            target_id=record.target_id,
            details=record.details,
            created_at=record.created_at,
        )
        for record in records
    ]


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
    except DeviceBindingError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
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
