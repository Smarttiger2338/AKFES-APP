from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from .auth import bearer_token, get_license_service
from .license_service import InvalidSessionError

router = APIRouter(tags=["authentication"])


class LogoutResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    logged_out: bool
    session_id: int
    revoked_at: int
    deleted_challenges: int


@router.post("/auth/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_akfes_device_id: Annotated[str | None, Header()] = None,
) -> LogoutResponse:
    token = bearer_token(authorization)
    service = get_license_service(request)
    try:
        session = service.verify_session(token, device_id=x_akfes_device_id)
    except (InvalidSessionError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from error

    revoked_at = int(time.time())
    with service.store.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """
            UPDATE sessions
            SET revoked_at = ?
            WHERE id = ? AND revoked_at IS NULL
            """,
            (revoked_at, session.session_id),
        )
        if cursor.rowcount != 1:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session",
            )
        challenge_cursor = connection.execute(
            "DELETE FROM request_challenges WHERE session_id = ? AND used_at IS NULL",
            (session.session_id,),
        )
        deleted_challenges = max(challenge_cursor.rowcount, 0)
        service.store.record_audit(
            action="session.logout",
            actor="client",
            target_type="session",
            target_id=str(session.session_id),
            details={
                "license_id": session.license_id,
                "revoked_at": revoked_at,
                "deleted_challenges": deleted_challenges,
            },
            created_at=revoked_at,
        )

    return LogoutResponse(
        logged_out=True,
        session_id=session.session_id,
        revoked_at=revoked_at,
        deleted_challenges=deleted_challenges,
    )
