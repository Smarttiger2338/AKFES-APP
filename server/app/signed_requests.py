from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from .auth import bearer_token
from .license_service import InvalidSessionError
from .request_security import (
    InvalidChallengeError,
    InvalidSignatureError,
    RequestSecurityService,
    VerifiedRequest,
)

router = APIRouter(tags=["request-security"])


class ChallengeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    challenge: str
    expires_at: int
    algorithm: str = "HMAC-SHA256"
    canonical_version: str = "AKFES-V2"


class SignedCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=512)


class SignedCheckResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    valid: bool
    license_id: int
    session_id: int
    challenge_id: int
    device_id: str | None


def get_request_security(request: Request) -> RequestSecurityService:
    return request.app.state.request_security


async def verify_signed_request(
    request: Request,
    *,
    authorization: str | None,
    challenge: str | None,
    signature: str | None,
    device_id: str | None,
) -> VerifiedRequest:
    session_token = bearer_token(authorization)
    if challenge is None or signature is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing challenge or request signature",
        )

    body = await request.body()
    try:
        return get_request_security(request).verify_request(
            session_token=session_token,
            challenge=challenge,
            signature=signature,
            method=request.method,
            path=request.url.path,
            body=body,
            device_id=device_id,
        )
    except InvalidSessionError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from error
    except InvalidChallengeError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Challenge is invalid, expired, or already used",
        ) from error
    except InvalidSignatureError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid request signature",
        ) from error


@router.post("/auth/challenge", response_model=ChallengeResponse)
def issue_challenge(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_akfes_device_id: Annotated[str | None, Header()] = None,
) -> ChallengeResponse:
    session_token = bearer_token(authorization)
    try:
        issued = get_request_security(request).issue_challenge(
            session_token=session_token,
            device_id=x_akfes_device_id,
        )
    except (InvalidSessionError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from error

    return ChallengeResponse(
        challenge=issued.challenge,
        expires_at=issued.expires_at,
    )


@router.post("/auth/signed-check", response_model=SignedCheckResponse)
async def signed_check(
    payload: SignedCheckRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_akfes_challenge: Annotated[str | None, Header()] = None,
    x_akfes_signature: Annotated[str | None, Header()] = None,
    x_akfes_device_id: Annotated[str | None, Header()] = None,
) -> SignedCheckResponse:
    verified = await verify_signed_request(
        request,
        authorization=authorization,
        challenge=x_akfes_challenge,
        signature=x_akfes_signature,
        device_id=x_akfes_device_id,
    )
    return SignedCheckResponse(
        valid=True,
        license_id=verified.license_id,
        session_id=verified.session_id,
        challenge_id=verified.challenge_id,
        device_id=verified.device_id,
    )
